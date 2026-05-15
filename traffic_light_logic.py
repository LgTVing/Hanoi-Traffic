import json
import os
import time

from config import *


class Intersection:
    """
    Pha đèn 8 bước không cắt luồng:
      0: NS_STRAIGHT  | 1: ALL_RED
      2: NS_LEFT      | 3: ALL_RED
      4: EW_STRAIGHT  | 5: ALL_RED
      6: EW_LEFT      | 7: ALL_RED
    """

    # Cache du lieu file theo chu ky doc.
    _lane_map_by_pos = None
    _lane_totals = [0] * LIGHT_INPUT_LANE_TOTAL
    _last_file_read_real = 0.0
    _last_output_real = 0.0

    @classmethod
    def set_layout_positions(cls, positions):
        # Luu vi tri cac nut giao de map lane theo thu tu NW/NE/SW/SE.
        cls._lane_map_by_pos = cls._build_lane_map(positions)

    @classmethod
    def _build_lane_map(cls, positions):
        xs = sorted({x for x, _ in positions})
        ys = sorted({y for _, y in positions})

        if len(xs) < 2 or len(ys) < 2:
            return {}

        # y nho hon la phia Bac, x nho hon la phia Tay.
        quad_map = {
            (0, 0): {EAST: 0, WEST: 3, SOUTH: 10, NORTH: 9},
            (1, 0): {EAST: 1, WEST: 2, SOUTH: 14, NORTH: 13},
            (0, 1): {EAST: 4, WEST: 7, SOUTH: 11, NORTH: 8},
            (1, 1): {EAST: 5, WEST: 6, SOUTH: 15, NORTH: 12},
        }

        lane_map = {}
        for x, y in positions:
            x_rank = xs.index(x)
            y_rank = ys.index(y)
            lane_map[(x, y)] = quad_map.get((x_rank, y_rank), {})

        return lane_map

    @staticmethod
    def _safe_int(value):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return 0

    @classmethod
    def _lane_totals_from_json_payload(cls, payload, lane_total):
        # Ho tro JSON tu thiet bi: {timestamp, device_id, data:[{lane,cars,bikes}]}
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

        totals = [0] * lane_total
        for item in items:
            if not isinstance(item, dict):
                continue

            lane_id = cls._safe_int(item.get("lane"))
            if lane_id < 0 or lane_id >= lane_total:
                continue

            cars = cls._safe_int(item.get("cars"))
            bikes = cls._safe_int(item.get("bikes"))
            totals[lane_id] += cars * PCU_CAR + bikes * PCU_BIKE

        return totals

    @classmethod
    def _try_parse_json_lane_totals(cls, content, lane_total):
        if not content:
            return None

        if content[0] not in "{[":
            return None

        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            return None

        return cls._lane_totals_from_json_payload(payload, lane_total)

    @classmethod
    def _read_lane_totals_from_file(cls):
        lane_total = LIGHT_INPUT_LANE_TOTAL
        path = LIGHT_INPUT_FILE

        if not os.path.exists(path):
            return [0] * lane_total

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                return [0] * lane_total

            json_totals = cls._try_parse_json_lane_totals(content, lane_total)
            if json_totals is None:
                last_line = ""
                for line in reversed(content.splitlines()):
                    if line.strip():
                        last_line = line.strip()
                        break

                if last_line and last_line != content:
                    json_totals = cls._try_parse_json_lane_totals(last_line, lane_total)

            if json_totals is not None:
                return json_totals
            return [0] * lane_total
        except OSError:
            return [0] * lane_total

    @classmethod
    def write_phase_output(cls, intersections):
        # Ghi trang thai pha den ra file JSON de he thong ngoai doc.
        if not WRITE_PHASE_OUTPUT:
            return

        now = time.time()
        if now - cls._last_output_real < PHASE_OUTPUT_REFRESH_SEC:
            return

        cls._last_output_real = now
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

        payload = {
            "timestamp": int(now),
            "time": time_str,
            "data": [],
        }

        for idx, ic in enumerate(intersections):
            pending = ic.pending_next_phase if ic.pending_next_phase else ""
            payload["data"].append(
                {
                    "index": idx,
                    "cx": int(ic.cx),
                    "cy": int(ic.cy),
                    "phase_mode": ic.phase_mode,
                    "phase_index": ic.phase,
                    "timer": round(max(0.0, ic.timer), 2),
                    "green_elapsed": round(ic.green_elapsed, 2),
                    "pending_next": pending,
                }
            )

        try:
            with open(PHASE_OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except OSError:
            return

    @classmethod
    def _refresh_lane_data_if_needed(cls):
        if not USE_FILE_LIGHT_INPUT:
            return

        now = time.time()
        if now - cls._last_file_read_real < LIGHT_INPUT_REFRESH_SEC:
            return

        cls._last_file_read_real = now
        cls._lane_totals = cls._read_lane_totals_from_file()

    def _update_waiting_from_file(self):
        if not USE_FILE_LIGHT_INPUT:
            return

        self._refresh_lane_data_if_needed()
        if not self._lane_map_by_pos:
            return

        mapping = self._lane_map_by_pos.get((self.cx, self.cy), {})
        totals = self._lane_totals

        def _lane_total(idx):
            if idx is None or idx < 0 or idx >= len(totals):
                return 0
            return totals[idx]

        for direction in (NORTH, SOUTH, EAST, WEST):
            self.waiting_counts[direction] = _lane_total(mapping.get(direction))

    def __init__(self, cx, cy):
        # Tâm hình học của nút giao, dùng làm gốc tính vị trí đèn và vùng dừng xe.
        self.cx = cx
        self.cy = cy

        # phase: chỉ số bước trong chu kỳ 0..7.
        # phase_mode: nhãn dễ đọc để module xe kiểm tra quyền đi.
        self.phase = 0
        self.phase_mode = "NS_STRAIGHT"

        # timer đếm ngược theo giây; khi chạm 0 sẽ chuyển pha.
        self.timer = MIN_GREEN_TIME
        self.green_elapsed = 0.0

        # Số xe chờ theo hướng (cập nhật từ VehicleController mỗi frame).
        # waiting_counts càng cao thì pha xanh tương ứng càng được kéo dài (trong giới hạn trần).
        self.waiting_counts = {NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0}

        # Dem thoi gian do theo truc NS/EW de khong cho vuot qua gioi han.
        self.red_elapsed_by_axis = {"NS": 0.0, "EW": 0.0}
        # Ghi nho truc xanh gan nhat va so pha xanh lien tiep.
        self.last_green_axis = self._axis_of_mode(self.phase_mode)
        self.axis_green_streak = 1 if self.last_green_axis else 0
        # Hysteresis cho ep chuyen truc theo chenh lech nhu cau.
        self.axis_demand_gap_hold = 0.0

        # Thời gian đỏ toàn hướng giữa các pha xanh để tách xung đột giao cắt.
        self.all_red_time = 0.8
        # Pha xanh ke tiep uu tien (neu can phuc vu re trai).
        self.pending_next_phase = None
        # Ghi nho loai pha xanh gan nhat de luan phien cong bang.
        self.last_phase_kind = None
        # Thoi gian cho tich luy theo tung pha (giay).
        self.wait_time_by_phase = {
            "NS_STRAIGHT": 0.0,
            "NS_LEFT": 0.0,
            "EW_STRAIGHT": 0.0,
            "EW_LEFT": 0.0,
        }
        # Hysteresis de tranh dao pha lien tuc.
        self.pressure_gap_hold = 0.0

    def _get_turn_ratios(self):
        weights = TURN_INTENTION_WEIGHTS
        total = sum(weights) if weights else 1.0
        if total <= 0:
            return 0.5, 0.3

        straight = weights[0] / total if len(weights) > 0 else 0.5
        left = weights[1] / total if len(weights) > 1 else 0.3
        return straight, left

    def _get_phase_pcu(self):
        ns_q = self.waiting_counts[NORTH] + self.waiting_counts[SOUTH]
        ew_q = self.waiting_counts[EAST] + self.waiting_counts[WEST]
        straight, left = self._get_turn_ratios()
        return {
            "NS_STRAIGHT": ns_q * straight,
            "NS_LEFT": ns_q * left,
            "EW_STRAIGHT": ew_q * straight,
            "EW_LEFT": ew_q * left,
        }

    def _get_axis_demand(self):
        ns_q = self.waiting_counts[NORTH] + self.waiting_counts[SOUTH]
        ew_q = self.waiting_counts[EAST] + self.waiting_counts[WEST]
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
        if MAX_RED_TIME_SEC <= 0:
            return None

        ns_red = self.red_elapsed_by_axis.get("NS", 0.0)
        ew_red = self.red_elapsed_by_axis.get("EW", 0.0)

        if ns_red < MAX_RED_TIME_SEC and ew_red < MAX_RED_TIME_SEC:
            return None
        return "NS" if ns_red >= ew_red else "EW"

    def _pick_axis_by_streak(self):
        if MAX_CONSECUTIVE_AXIS_GREENS <= 0:
            return None
        if self.axis_green_streak < MAX_CONSECUTIVE_AXIS_GREENS:
            return None
        return self._other_axis(self.last_green_axis)

    def _pick_axis_by_demand(self, dt):
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
        phase_pcu = self._get_phase_pcu()
        return phase_pcu.get(mode, 0.0) * self.wait_time_by_phase.get(mode, 0.0)

    def _phase_min_max(self, mode):
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
        # Cong bang: luan phien STRAIGHT <-> LEFT giua cac pha xanh.
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
        required_kind = self._required_next_kind()
        next_mode, _ = self._select_best_phase(
            required_kind=required_kind,
            axis_filter=axis_filter,
        )
        self.pending_next_phase = next_mode

    def _enter_phase(self, mode):
        phase_index_map = {
            "NS_STRAIGHT": 0,
            "ALL_RED": 1,
            "NS_LEFT": 2,
            "EW_STRAIGHT": 4,
            "EW_LEFT": 6,
        }

        self.phase_mode = mode
        self.phase = phase_index_map.get(mode, 0)
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
        # Neu dung du lieu file thi cap nhat waiting_counts truoc khi tinh pha.
        self._update_waiting_from_file()
        self._update_wait_times(dt)
        self._update_red_elapsed(dt)

        if self.phase_mode != "ALL_RED":
            self.green_elapsed += dt

        # Bước 1: đếm lùi theo thời gian frame hiện tại.
        self.timer -= dt

        # if: nếu timer vẫn dương thì chưa đến lúc chuyển pha.
        if self.timer > 0:
            return

        starved_axis = self._pick_starved_axis()
        streak_axis = self._pick_axis_by_streak()
        required_axis = starved_axis if starved_axis else streak_axis

        # all_red -> chon pha xanh tiep theo (khong xung dot).
        if self.phase_mode == "ALL_RED":
            if required_axis:
                required_kind = self._required_next_kind()
                next_mode, _ = self._select_best_phase(
                    required_kind=required_kind,
                    axis_filter=required_axis,
                )
                self._enter_phase(next_mode)
                return

            if self.pending_next_phase:
                self._enter_phase(self.pending_next_phase)
            else:
                required_kind = self._required_next_kind()
                next_mode, _ = self._select_best_phase(required_kind=required_kind)
                self._enter_phase(next_mode)
            return

        # Kiem tra gia han hay chuyen pha xanh.
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

        if self.green_elapsed < min_g:
            self.timer = min_g - self.green_elapsed
            return

        if early_axis:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return

        if self.green_elapsed >= max_g:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return

        if pressure_gap >= PRESSURE_SWITCH_DELTA:
            self.pressure_gap_hold += dt
        else:
            self.pressure_gap_hold = 0.0

        if best_mode and self.pressure_gap_hold >= PRESSURE_SWITCH_HOLD_SEC:
            self._plan_next_phase_after_green(axis_filter)
            self._enter_phase("ALL_RED")
            return

        if current_pcu > 0 and self.green_elapsed + PASSAGE_TIME <= max_g:
            self.timer = PASSAGE_TIME
            return

        self._plan_next_phase_after_green(axis_filter)
        self._enter_phase("ALL_RED")

    def is_allowed(self, direction, turn_intention):
        # Quy tắc đặc biệt: rẽ phải luôn được phép (mô phỏng luồng tách riêng/slip lane).
        if turn_intention == "RIGHT":
            return True

        # Chuẩn hóa intention lạ về STRAIGHT để tránh lỗi do dữ liệu bẩn.
        if turn_intention not in ["STRAIGHT", "LEFT", "RIGHT"]:
            turn_intention = "STRAIGHT"

        # Nếu ALL_RED thì khóa toàn bộ luồng (trừ rẽ phải đã return phía trên).
        if self.phase_mode == "ALL_RED":
            return False

        # Phân loại hướng theo trục dọc/ngang để so với pha hiện tại.
        ns = direction in [NORTH, SOUTH]
        ew = direction in [EAST, WEST]

        # Các nhánh if dưới đây ánh xạ trực tiếp: "mode nào -> kiểu xe nào được đi".
        if self.phase_mode == "NS_STRAIGHT":
            return ns and turn_intention == "STRAIGHT"
        if self.phase_mode == "NS_LEFT":
            return ns and turn_intention == "LEFT"
        if self.phase_mode == "EW_STRAIGHT":
            return ew and turn_intention == "STRAIGHT"
        if self.phase_mode == "EW_LEFT":
            return ew and turn_intention == "LEFT"
        return False

    def get_display_mode_for_direction(self, direction):
        # Hàm này chỉ phục vụ hiển thị icon đèn (không quyết định vật lý xe).
        if self.phase_mode == "ALL_RED":
            return "RED"

        # if: cột đèn hướng Bắc/Nam.
        if direction in [NORTH, SOUTH]:
            if self.phase_mode == "NS_STRAIGHT":
                return "STRAIGHT"
            if self.phase_mode == "NS_LEFT":
                return "LEFT"
            return "RED"

        # if: cột đèn hướng Đông/Tây.
        if direction in [EAST, WEST]:
            if self.phase_mode == "EW_STRAIGHT":
                return "STRAIGHT"
            if self.phase_mode == "EW_LEFT":
                return "LEFT"
            return "RED"

        # Fallback cho direction không hợp lệ.
        return "RED"
