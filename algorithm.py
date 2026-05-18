import json
import math
import threading
import time
import uuid

import paho.mqtt.client as mqtt

# --- CAU HINH MQTT TU PROTOCOL.MD ---
BROKER = "127.0.0.1"
PORT = 1883
TOPIC_TELEMETRY = "traffic/telemetry"
TOPIC_CONTROL = "traffic/lights"

# --- BANG MAPPING LAN DUONG (Tu PROTOCOL.md) ---
INTERSECTIONS = {
    0: {"N": 10, "E": 3, "S": 9, "W": 0},
    1: {"N": 14, "E": 2, "S": 13, "W": 1},
    2: {"N": 11, "E": 7, "S": 8, "W": 4},
    3: {"N": 15, "E": 6, "S": 12, "W": 5},
}

# --- THAM SO THUAT TOAN (GIU NGUYEN TU LOGIC HIEN TAI) ---
PCU_CAR = 1.0
PCU_BIKE = 0.25

MIN_GREEN_TIME = 15.0
MAX_GREEN_TIME = 35.0
LEFT_MIN_GREEN_TIME = max(2.0, MIN_GREEN_TIME * 0.6)
LEFT_MAX_GREEN_TIME = MAX_GREEN_TIME * 0.8
ALL_RED_TIME = 0.8
PASSAGE_TIME = 2.0
PRESSURE_SWITCH_DELTA = 2.0
PRESSURE_SWITCH_HOLD_SEC = 2.0

MAX_RED_TIME_SEC = 65.0
RED_DEMAND_MIN = 0.5
MAX_CONSECUTIVE_AXIS_GREENS = 2
AXIS_DEMAND_SWITCH_DELTA = 6.0
AXIS_DEMAND_SWITCH_HOLD_SEC = 1.0

TURN_INTENTION_WEIGHTS = [0.45, 0.30, 0.25]

# --- THAM SO VAN HANH VONG LAP ---
LANE_TOTAL = 16
TELEMETRY_STALE_SEC = 5.0
PUBLISH_INTERVAL_SEC = 0.5
LOOP_SLEEP_SEC = 0.05

DIRECTIONS = ("N", "S", "E", "W")


def _safe_int(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


class TelemetryBuffer:
    """Luu du lieu tu MQTT de logic su dung theo nhip update."""

    def __init__(self, lane_total):
        self._lane_total = lane_total
        self._lock = threading.Lock()
        self._lane_pcu = [0.0] * lane_total
        self._last_update_real = 0.0
        self._last_payload_ts = None

    def _lane_totals_from_payload(self, payload):
        # Ho tro JSON: {timestamp, device_id, data:[{lane,cars,bikes}]}
        items = None

        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            items = payload.get("data")
        elif isinstance(payload, list):
            if payload and isinstance(payload[-1], dict) and isinstance(payload[-1].get("data"), list):
                items = payload[-1].get("data")
            elif payload and isinstance(payload[0], dict) and "lane" in payload[0]:
                items = payload

        if not isinstance(items, list):
            return None

        totals = [0.0] * self._lane_total
        for item in items:
            if not isinstance(item, dict):
                continue
            lane_id = _safe_int(item.get("lane"))
            if lane_id < 0 or lane_id >= self._lane_total:
                continue
            cars = _safe_int(item.get("cars"))
            bikes = _safe_int(item.get("bikes"))
            totals[lane_id] += cars * PCU_CAR + bikes * PCU_BIKE
        return totals

    def update_from_payload(self, payload):
        totals = self._lane_totals_from_payload(payload)
        if totals is None:
            return
        with self._lock:
            self._lane_pcu = totals
            self._last_update_real = time.time()
            if isinstance(payload, dict):
                self._last_payload_ts = payload.get("timestamp")

    def get_lane_pcu(self):
        with self._lock:
            if TELEMETRY_STALE_SEC > 0 and time.time() - self._last_update_real > TELEMETRY_STALE_SEC:
                return [0.0] * self._lane_total
            return list(self._lane_pcu)


class IntersectionController:
    """Dieu khien pha den cho mot nut giao theo thuat toan toi uu."""

    def __init__(self, intersection_id, lane_map):
        # Luu id va mapping lane->huong vao nut giao.
        self.intersection_id = intersection_id
        self.lane_map = lane_map

        # Pha ban dau: Bac-Nam di thang.
        self.phase = 0
        self.phase_mode = "NS_STRAIGHT"
        self.timer = MIN_GREEN_TIME
        self.green_elapsed = 0.0

        # So xe cho theo huong.
        self.waiting_counts = {"N": 0.0, "S": 0.0, "E": 0.0, "W": 0.0}

        # Dem thoi gian do theo truc NS/EW de chong doi.
        self.red_elapsed_by_axis = {"NS": 0.0, "EW": 0.0}
        self.last_green_axis = self._axis_of_mode(self.phase_mode)
        self.axis_green_streak = 1 if self.last_green_axis else 0
        self.axis_demand_gap_hold = 0.0

        # Thoi gian do toan bo giua cac pha.
        self.all_red_time = ALL_RED_TIME
        self.pending_next_phase = None
        self.last_phase_kind = None
        self.wait_time_by_phase = {
            "NS_STRAIGHT": 0.0,
            "NS_LEFT": 0.0,
            "EW_STRAIGHT": 0.0,
            "EW_LEFT": 0.0,
        }
        self.pressure_gap_hold = 0.0
        self._phase_changed = False

    def update_waiting_from_lanes(self, lane_pcu):
        # Cap nhat hang cho theo mapping lane do camera gui ve.
        for direction in DIRECTIONS:
            lane_id = self.lane_map.get(direction)
            if lane_id is None or lane_id < 0 or lane_id >= len(lane_pcu):
                self.waiting_counts[direction] = 0.0
            else:
                self.waiting_counts[direction] = lane_pcu[lane_id]

    def _get_turn_ratios(self):
        # Uoc tinh ti le xe di thang va re trai.
        weights = TURN_INTENTION_WEIGHTS
        total = sum(weights) if weights else 1.0
        if total <= 0:
            return 0.5, 0.3
        straight = weights[0] / total if len(weights) > 0 else 0.5
        left = weights[1] / total if len(weights) > 1 else 0.3
        return straight, left

    def _get_phase_pcu(self):
        # Uoc tinh luong xe cho theo tung pha (di thang/re trai).
        ns_q = self.waiting_counts["N"] + self.waiting_counts["S"]
        ew_q = self.waiting_counts["E"] + self.waiting_counts["W"]
        straight, left = self._get_turn_ratios()
        return {
            "NS_STRAIGHT": ns_q * straight,
            "NS_LEFT": ns_q * left,
            "EW_STRAIGHT": ew_q * straight,
            "EW_LEFT": ew_q * left,
        }

    def _get_axis_demand(self):
        # Tong nhu cau theo truc NS/EW.
        ns_q = self.waiting_counts["N"] + self.waiting_counts["S"]
        ew_q = self.waiting_counts["E"] + self.waiting_counts["W"]
        return {"NS": ns_q, "EW": ew_q}

    @staticmethod
    def _axis_of_mode(mode):
        if not mode:
            return None
        if mode.startswith("NS_"):
            return "NS"
        if mode.startswith("EW_"):
            return "EW"
        return None

    @staticmethod
    def _other_axis(axis):
        if axis == "NS":
            return "EW"
        if axis == "EW":
            return "NS"
        return None

    def _update_red_elapsed(self, dt):
        # Cap nhat thoi gian do cua tung truc (chong doi).
        axis_demand = self._get_axis_demand()
        current_axis = self._axis_of_mode(self.phase_mode)

        for axis in ("NS", "EW"):
            demand = axis_demand.get(axis, 0.0)
            if demand <= RED_DEMAND_MIN:
                self.red_elapsed_by_axis[axis] = 0.0
                continue
            if self.phase_mode != "ALL_RED" and current_axis == axis:
                self.red_elapsed_by_axis[axis] = 0.0
                continue
            self.red_elapsed_by_axis[axis] += dt

    def _pick_starved_axis(self):
        # Neu co truc cho do qua lau thi ep chuyen sang truc do.
        if MAX_RED_TIME_SEC <= 0:
            return None
        ns_red = self.red_elapsed_by_axis.get("NS", 0.0)
        ew_red = self.red_elapsed_by_axis.get("EW", 0.0)
        if ns_red < MAX_RED_TIME_SEC and ew_red < MAX_RED_TIME_SEC:
            return None
        return "NS" if ns_red >= ew_red else "EW"

    def _pick_axis_by_streak(self):
        # Ep doi truc neu cung mot truc da xanh qua nhieu lan lien tiep.
        if MAX_CONSECUTIVE_AXIS_GREENS <= 0:
            return None
        if self.axis_green_streak < MAX_CONSECUTIVE_AXIS_GREENS:
            return None
        return self._other_axis(self.last_green_axis)

    def _pick_axis_by_demand(self, dt):
        # Rut ngan pha xanh neu chenh lech nhu cau giua 2 truc qua lon.
        if self.phase_mode == "ALL_RED":
            self.axis_demand_gap_hold = 0.0
            return None

        axis_demand = self._get_axis_demand()
        diff = axis_demand.get("NS", 0.0) - axis_demand.get("EW", 0.0)
        if abs(diff) < AXIS_DEMAND_SWITCH_DELTA:
            self.axis_demand_gap_hold = 0.0
            return None

        high_axis = "NS" if diff > 0 else "EW"
        current_axis = self._axis_of_mode(self.phase_mode)
        if current_axis == high_axis:
            self.axis_demand_gap_hold = 0.0
            return None

        self.axis_demand_gap_hold += dt
        if self.axis_demand_gap_hold >= AXIS_DEMAND_SWITCH_HOLD_SEC:
            return high_axis
        return None

    def _update_wait_times(self, dt):
        # Tich luy thoi gian cho theo tung pha de tinh pressure.
        phase_pcu = self._get_phase_pcu()
        for mode, pcu in phase_pcu.items():
            if pcu <= 0:
                self.wait_time_by_phase[mode] = 0.0
                continue
            if self.phase_mode == mode:
                self.wait_time_by_phase[mode] = max(0.0, self.wait_time_by_phase[mode] - dt)
            else:
                self.wait_time_by_phase[mode] += dt

    def _phase_pressure(self, mode):
        # Ap luc = luong xe * thoi gian cho tich luy.
        phase_pcu = self._get_phase_pcu()
        return phase_pcu.get(mode, 0.0) * self.wait_time_by_phase.get(mode, 0.0)

    def _phase_min_max(self, mode):
        # Tra ve gioi han thoi gian xanh theo loai pha.
        if mode in ("NS_LEFT", "EW_LEFT"):
            return LEFT_MIN_GREEN_TIME, LEFT_MAX_GREEN_TIME
        return MIN_GREEN_TIME, MAX_GREEN_TIME

    @staticmethod
    def _phase_kind(mode):
        if mode.endswith("STRAIGHT"):
            return "STRAIGHT"
        if mode.endswith("LEFT"):
            return "LEFT"
        return None

    def _required_next_kind(self):
        # Cong bang: luon luan phien STRAIGHT <-> LEFT.
        if self.phase_mode != "ALL_RED":
            current_kind = self._phase_kind(self.phase_mode)
            if current_kind == "STRAIGHT":
                return "LEFT"
            if current_kind == "LEFT":
                return "STRAIGHT"
            return None

        if self.last_phase_kind == "STRAIGHT":
            return "LEFT"
        if self.last_phase_kind == "LEFT":
            return "STRAIGHT"
        return None

    def _select_best_phase(self, exclude=None, required_kind=None, axis_filter=None):
        # Chon pha co ap luc cao nhat trong tap hop duoc phep.
        phases = ["NS_STRAIGHT", "NS_LEFT", "EW_STRAIGHT", "EW_LEFT"]
        if axis_filter:
            phases = [mode for mode in phases if mode.startswith(axis_filter)]
        if required_kind:
            phases = [mode for mode in phases if mode.endswith(required_kind)]
        if exclude:
            phases = [mode for mode in phases if mode != exclude]

        best_mode = None
        best_pressure = -1.0
        for mode in phases:
            pressure = self._phase_pressure(mode)
            if pressure > best_pressure:
                best_pressure = pressure
                best_mode = mode

        if best_mode is None:
            best_mode = phases[0] if phases else "NS_STRAIGHT"
            best_pressure = self._phase_pressure(best_mode)

        return best_mode, best_pressure

    def _plan_next_phase_after_green(self, axis_filter=None):
        # Len lich pha xanh tiep theo (sau ALL_RED).
        required_kind = self._required_next_kind()
        next_mode, _ = self._select_best_phase(
            required_kind=required_kind,
            axis_filter=axis_filter,
        )
        self.pending_next_phase = next_mode

    def _enter_phase(self, mode):
        # Cap nhat trang thai khi vao mot pha moi.
        phase_index_map = {
            "NS_STRAIGHT": 0,
            "ALL_RED": 1,
            "NS_LEFT": 2,
            "EW_STRAIGHT": 4,
            "EW_LEFT": 6,
        }

        self.phase_mode = mode
        self.phase = phase_index_map.get(mode, 0)
        self._phase_changed = True

        if mode != "ALL_RED":
            self.pending_next_phase = None
            self.last_phase_kind = self._phase_kind(mode)
            axis = self._axis_of_mode(mode)
            if axis:
                if axis == self.last_green_axis:
                    self.axis_green_streak += 1
                else:
                    self.axis_green_streak = 1
                    self.last_green_axis = axis
            self.axis_demand_gap_hold = 0.0

        self.pressure_gap_hold = 0.0

        if mode == "ALL_RED":
            self.timer = self.all_red_time
            self.green_elapsed = 0.0
            return

        min_g, _ = self._phase_min_max(mode)
        self.timer = min_g
        self.green_elapsed = 0.0

    def update(self, dt):
        # Reset co thay doi pha cho moi tick.
        self._phase_changed = False

        # B1: cap nhat wait time va red time theo du lieu hien tai.
        self._update_wait_times(dt)
        self._update_red_elapsed(dt)

        if self.phase_mode != "ALL_RED":
            self.green_elapsed += dt

        # B2: dem lui theo dt.
        self.timer -= dt
        if self.timer > 0:
            return self._phase_changed

        # B3: kiem tra ep doi truc theo doi/muc gioi han.
        starved_axis = self._pick_starved_axis()
        streak_axis = self._pick_axis_by_streak()
        required_axis = starved_axis if starved_axis else streak_axis

        # B4: neu dang ALL_RED thi chon pha xanh tiep theo.
        if self.phase_mode == "ALL_RED":
            if required_axis:
                required_kind = self._required_next_kind()
                next_mode, _ = self._select_best_phase(
                    required_kind=required_kind,
                    axis_filter=required_axis,
                )
                self._enter_phase(next_mode)
                return self._phase_changed

            if self.pending_next_phase:
                self._enter_phase(self.pending_next_phase)
            else:
                required_kind = self._required_next_kind()
                next_mode, _ = self._select_best_phase(required_kind=required_kind)
                self._enter_phase(next_mode)
            return self._phase_changed

        # B5: tinh toan chuyen pha khi dang xanh.
        min_g, max_g = self._phase_min_max(self.phase_mode)
        phase_pcu = self._get_phase_pcu()
        current_pcu = phase_pcu.get(self.phase_mode, 0.0)
        current_pressure = self._phase_pressure(self.phase_mode)
        required_kind = self._required_next_kind()
        current_axis = self._axis_of_mode(self.phase_mode)
        demand_axis = self._pick_axis_by_demand(dt)

        early_axis = None
        if starved_axis and current_axis != starved_axis:
            early_axis = starved_axis
        elif demand_axis and current_axis != demand_axis:
            if required_axis is None or required_axis == demand_axis:
                early_axis = demand_axis

        axis_filter = required_axis or early_axis

        best_mode, best_pressure = self._select_best_phase(
            exclude=self.phase_mode,
            required_kind=required_kind,
            axis_filter=axis_filter,
        )
        pressure_gap = best_pressure - current_pressure

        # B6: chua dat min green thi giu pha.
        if self.green_elapsed < min_g:
            self.timer = min_g - self.green_elapsed
            return self._phase_changed

        # B7: neu can ep chuyen truc som thi chuyen ALL_RED.
        if early_axis:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return self._phase_changed

        # B8: het max green thi chuyen pha.
        if self.green_elapsed >= max_g:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return self._phase_changed

        # B9: doi pha neu ap luc ben kia cao hon trong khoang hysteresis.
        if pressure_gap >= PRESSURE_SWITCH_DELTA:
            self.pressure_gap_hold += dt
        else:
            self.pressure_gap_hold = 0.0

        if best_mode and self.pressure_gap_hold >= PRESSURE_SWITCH_HOLD_SEC:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return self._phase_changed

        # B10: neu van con xe qua nut thi gia han PASSAGE_TIME.
        if current_pcu > 0 and self.green_elapsed + PASSAGE_TIME <= max_g:
            self.timer = PASSAGE_TIME
            return self._phase_changed

        # B11: fallback chuyen pha qua ALL_RED.
        self._plan_next_phase_after_green(axis_filter)
        self._enter_phase("ALL_RED")
        return self._phase_changed

    def build_lane_commands(self):
        # Chuyen trang thai pha sang lenh theo lane.
        duration = max(1, int(math.ceil(self.timer)))
        commands = []

        for direction in ("N", "S", "E", "W"):
            lane_id = self.lane_map.get(direction)
            if lane_id is None:
                continue

            straight_state = "red"
            left_state = "red"

            if self.phase_mode == "NS_STRAIGHT" and direction in ("N", "S"):
                straight_state = "green"
            elif self.phase_mode == "NS_LEFT" and direction in ("N", "S"):
                left_state = "green"
            elif self.phase_mode == "EW_STRAIGHT" and direction in ("E", "W"):
                straight_state = "green"
            elif self.phase_mode == "EW_LEFT" and direction in ("E", "W"):
                left_state = "green"

            commands.append(
                {
                    "lane_id": lane_id,
                    "straight": {"state": straight_state, "duration": duration},
                    "left": {"state": left_state, "duration": duration},
                }
            )

        return commands


telemetry_buffer = TelemetryBuffer(LANE_TOTAL)


def on_connect(client, userdata, flags, rc, properties=None):
    print(f"✅ Da ket noi toi MQTT Broker tai {BROKER}")
    client.subscribe(TOPIC_TELEMETRY)
    print(f"📡 Dang lang nghe du lieu xe tu: {TOPIC_TELEMETRY}")


def on_message(client, userdata, msg):
    # Nhan du lieu tu camera/AI va cap nhat vao buffer.
    try:
        payload = json.loads(msg.payload.decode())
        telemetry_buffer.update_from_payload(payload)
        print(
            f"[Telemetry] ts={payload.get('timestamp', 'N/A')} lane0={payload.get('data', [{}])[0].get('cars', 0)}"
        )
    except Exception:
        pass


def build_command_payload(controllers):
    # Dong goi JSON theo dung cau truc PROTOCOL.md.
    payload = {
        "timestamp": int(time.time()),
        "command_id": f"cmd-{str(uuid.uuid4())[:8]}",
        "intersections": [],
    }

    for ctrl in controllers:
        payload["intersections"].append(
            {
                "intersection_id": ctrl.intersection_id,
                "lanes": ctrl.build_lane_commands(),
            }
        )

    return payload


def run_simple_server():
    # Giu nguyen phan ket noi MQTT, chi thay logic dieu khien den.
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT, 60)
    except Exception as e:
        print(f"❌ Loi ket noi MQTT: {e}")
        return

    client.loop_start()

    controllers = [
        IntersectionController(int_id, lanes) for int_id, lanes in INTERSECTIONS.items()
    ]

    print("🚀 Bat dau dieu khien den theo thuat toan toi uu...")

    last_tick = time.time()
    last_publish = 0.0

    try:
        while True:
            now = time.time()
            dt = now - last_tick
            last_tick = now
            if dt <= 0:
                dt = LOOP_SLEEP_SEC
            dt = min(dt, 1.0)

            # B1: lay du lieu lane tu telemetry (neu mat tin hieu thi ve 0).
            lane_pcu = telemetry_buffer.get_lane_pcu()

            # B2: cap nhat tung nut giao va kiem tra co doi pha hay khong.
            phase_changed = False
            for ctrl in controllers:
                ctrl.update_waiting_from_lanes(lane_pcu)
                if ctrl.update(dt):
                    phase_changed = True

            # B3: gui lenh MQTT theo nhip hoac khi doi pha.
            if phase_changed or (now - last_publish) >= PUBLISH_INTERVAL_SEC:
                payload = build_command_payload(controllers)
                client.publish(TOPIC_CONTROL, json.dumps(payload))
                last_publish = now

            time.sleep(LOOP_SLEEP_SEC)

    except KeyboardInterrupt:
        print("\n🛑 Da ngat Server dieu khien.")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    run_simple_server()
