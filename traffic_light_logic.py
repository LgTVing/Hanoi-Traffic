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
    def _read_lane_totals_from_file(cls):
        lane_total = LIGHT_INPUT_LANE_TOTAL
        path = LIGHT_INPUT_FILE

        if not os.path.exists(path):
            return [0] * lane_total

        try:
            with open(path, "r", encoding="utf-8") as f:
                rows = [line.strip() for line in f if line.strip()]

            if len(rows) < 2:
                return [0] * lane_total

            last = rows[-1].split(",")
            expected = 2 + lane_total * 2
            if len(last) < expected:
                return [0] * lane_total

            values = last[2: 2 + lane_total * 2]
            totals = []
            for i in range(0, lane_total * 2, 2):
                cars = cls._safe_int(values[i])
                bikes = cls._safe_int(values[i + 1])
                totals.append(cars * PCU_CAR + bikes * PCU_BIKE)
            return totals
        except OSError:
            return [0] * lane_total

    @classmethod
    def write_phase_output(cls, intersections):
        # Ghi trang thai pha den ra file de he thong ngoai doc.
        if not WRITE_PHASE_OUTPUT:
            return

        now = time.time()
        if now - cls._last_output_real < PHASE_OUTPUT_REFRESH_SEC:
            return

        cls._last_output_real = now
        time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))

        header = "Time,Index,CX,CY,PhaseMode,PhaseIndex,Timer,GreenElapsed,PendingNext"
        lines = [header]

        for idx, ic in enumerate(intersections):
            pending = ic.pending_next_phase if ic.pending_next_phase else ""
            lines.append(
                "{t},{i},{x},{y},{mode},{phase},{timer:.2f},{elapsed:.2f},{pending}".format(
                    t=time_str,
                    i=idx,
                    x=int(ic.cx),
                    y=int(ic.cy),
                    mode=ic.phase_mode,
                    phase=ic.phase,
                    timer=max(0.0, ic.timer),
                    elapsed=ic.green_elapsed,
                    pending=pending,
                )
            )

        try:
            with open(PHASE_OUTPUT_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
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

        # Thời gian đỏ toàn hướng giữa các pha xanh để tách xung đột giao cắt.
        self.all_red_time = 0.8
        # Pha xanh ke tiep uu tien (neu can phuc vu re trai).
        self.pending_next_phase = None
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

    def _axis_left_phase(self, mode):
        if mode == "NS_STRAIGHT":
            return "NS_LEFT"
        if mode == "EW_STRAIGHT":
            return "EW_LEFT"
        return None

    def _has_left_demand(self, mode):
        left_mode = self._axis_left_phase(mode)
        if not left_mode:
            return False
        return self._phase_pressure(left_mode) >= LEFT_DEMAND_THRESHOLD

    def _select_best_phase(self, exclude=None):
        phases = ["NS_STRAIGHT", "NS_LEFT", "EW_STRAIGHT", "EW_LEFT"]
        best_mode = None
        best_pressure = -1.0

        for mode in phases:
            if mode == exclude:
                continue
            pressure = self._phase_pressure(mode)
            if pressure > best_pressure:
                best_pressure = pressure
                best_mode = mode

        if best_mode is None:
            best_mode = "NS_STRAIGHT"
            best_pressure = self._phase_pressure(best_mode)

        return best_mode, best_pressure

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

        if self.phase_mode != "ALL_RED":
            self.green_elapsed += dt

        # Bước 1: đếm lùi theo thời gian frame hiện tại.
        self.timer -= dt

        # if: nếu timer vẫn dương thì chưa đến lúc chuyển pha.
        if self.timer > 0:
            return

        # all_red -> chon pha xanh tiep theo (khong xung dot).
        if self.phase_mode == "ALL_RED":
            if self.pending_next_phase:
                self._enter_phase(self.pending_next_phase)
            else:
                next_mode, _ = self._select_best_phase()
                self._enter_phase(next_mode)
            return

        # Kiem tra gia han hay chuyen pha xanh.
        min_g, max_g = self._phase_min_max(self.phase_mode)
        phase_pcu = self._get_phase_pcu()
        current_pcu = phase_pcu.get(self.phase_mode, 0.0)
        current_pressure = self._phase_pressure(self.phase_mode)
        best_mode, best_pressure = self._select_best_phase(exclude=self.phase_mode)
        pressure_gap = best_pressure - current_pressure

        if self.green_elapsed < min_g:
            self.timer = min_g - self.green_elapsed
            return

        if self.green_elapsed >= max_g:
            if self._has_left_demand(self.phase_mode):
                self.pending_next_phase = self._axis_left_phase(self.phase_mode)
            self._enter_phase("ALL_RED")
            return

        if pressure_gap >= PRESSURE_SWITCH_DELTA:
            self.pressure_gap_hold += dt
        else:
            self.pressure_gap_hold = 0.0

        if best_mode and self.pressure_gap_hold >= PRESSURE_SWITCH_HOLD_SEC:
            if self._has_left_demand(self.phase_mode):
                self.pending_next_phase = self._axis_left_phase(self.phase_mode)
            self._enter_phase("ALL_RED")
            return

        if current_pcu > 0 and self.green_elapsed + PASSAGE_TIME <= max_g:
            self.timer = PASSAGE_TIME
            return

        if self._has_left_demand(self.phase_mode):
            self.pending_next_phase = self._axis_left_phase(self.phase_mode)
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
