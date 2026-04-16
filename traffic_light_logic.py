from config import *


class Intersection:
    """
    Pha đèn 8 bước không cắt luồng:
      0: NS_STRAIGHT  | 1: ALL_RED
      2: NS_LEFT      | 3: ALL_RED
      4: EW_STRAIGHT  | 5: ALL_RED
      6: EW_LEFT      | 7: ALL_RED
    """

    def __init__(self, cx, cy):
        # Tâm hình học của nút giao, dùng làm gốc tính vị trí đèn và vùng dừng xe.
        self.cx = cx
        self.cy = cy

        # phase: chỉ số bước trong chu kỳ 0..7.
        # phase_mode: nhãn dễ đọc để module xe kiểm tra quyền đi.
        self.phase = 0
        self.phase_mode = "NS_STRAIGHT"

        # timer đếm ngược theo giây; khi chạm 0 sẽ chuyển pha.
        self.timer = BASE_GREEN_TIME

        # Số xe chờ theo hướng (cập nhật từ VehicleController mỗi frame).
        # waiting_counts càng cao thì pha xanh tương ứng càng được kéo dài (trong giới hạn trần).
        self.waiting_counts = {NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0}

        # Thời gian đỏ toàn hướng giữa các pha xanh để tách xung đột giao cắt.
        self.all_red_time = 0.8

    def update(self, dt):
        # Bước 1: đếm lùi theo thời gian frame hiện tại.
        self.timer -= dt

        # if: nếu timer vẫn dương thì chưa đến lúc chuyển pha.
        if self.timer > 0:
            return

        # Bước 2: timer đã hết -> nhảy sang pha kế tiếp theo vòng tròn 0..7.
        self.phase = (self.phase + 1) % 8

        # if/elif theo phase để gán mode và thời lượng pha mới.
        # Pha thẳng dùng hệ số cộng theo hàng chờ lớn hơn pha rẽ trái.
        if self.phase == 0:
            self.phase_mode = "NS_STRAIGHT"
            ns_q = self.waiting_counts[NORTH] + self.waiting_counts[SOUTH]
            self.timer = min(MAX_GREEN_TIME, BASE_GREEN_TIME + ns_q * 0.8)
        elif self.phase == 1:
            self.phase_mode = "ALL_RED"
            self.timer = self.all_red_time
        elif self.phase == 2:
            self.phase_mode = "NS_LEFT"
            ns_q = self.waiting_counts[NORTH] + self.waiting_counts[SOUTH]
            self.timer = min(MAX_GREEN_TIME * 0.8, max(2.0, BASE_GREEN_TIME * 0.6 + ns_q * 0.5))
        elif self.phase == 3:
            self.phase_mode = "ALL_RED"
            self.timer = self.all_red_time
        elif self.phase == 4:
            self.phase_mode = "EW_STRAIGHT"
            ew_q = self.waiting_counts[EAST] + self.waiting_counts[WEST]
            self.timer = min(MAX_GREEN_TIME, BASE_GREEN_TIME + ew_q * 0.8)
        elif self.phase == 5:
            self.phase_mode = "ALL_RED"
            self.timer = self.all_red_time
        elif self.phase == 6:
            self.phase_mode = "EW_LEFT"
            ew_q = self.waiting_counts[EAST] + self.waiting_counts[WEST]
            self.timer = min(MAX_GREEN_TIME * 0.8, max(2.0, BASE_GREEN_TIME * 0.6 + ew_q * 0.5))
        elif self.phase == 7:
            self.phase_mode = "ALL_RED"
            self.timer = self.all_red_time

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
