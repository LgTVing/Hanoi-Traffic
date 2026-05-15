from config import *


class Intersection:
    """
    Quản lý trạng thái đèn giao thông theo lane được điều khiển từ MQTT.
    """

    def __init__(self, cx, cy, intersection_id=0):
        # Tâm hình học của nút giao.
        self.cx = cx
        self.cy = cy
        self.intersection_id = intersection_id

        # Khởi tạo lane mapping theo protocol
        self.lane_mapping = {}
        if intersection_id == 0:
            self.lane_mapping = {NORTH: 10, EAST: 3, SOUTH: 9, WEST: 0}
        elif intersection_id == 1:
            self.lane_mapping = {NORTH: 14, EAST: 2, SOUTH: 13, WEST: 1}
        elif intersection_id == 2:
            self.lane_mapping = {NORTH: 11, EAST: 7, SOUTH: 8, WEST: 4}
        elif intersection_id == 3:
            self.lane_mapping = {NORTH: 15, EAST: 6, SOUTH: 12, WEST: 5}

        # Ánh xạ ngược từ lane_id sang hướng (direction)
        self.lane_to_dir = {v: k for k, v in self.lane_mapping.items()}

        # Trạng thái đèn của mỗi hướng (mặc định tất cả đều đỏ)
        self.lights = {
            direction: {
                "straight": {"state": "red", "timer": 0},
                "left": {"state": "red", "timer": 0}
            } for direction in [NORTH, EAST, SOUTH, WEST]
        }

        # Số xe chờ theo hướng (cập nhật từ VehicleController mỗi frame).
        self.waiting_counts = {NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0}

    def update(self, dt):
        # Trừ timer đếm ngược, hiện tại chỉ để hiển thị hoặc xử lý sau này
        for d in self.lights:
            for action in ["straight", "left"]:
                if self.lights[d][action]["timer"] > 0:
                    self.lights[d][action]["timer"] -= dt
                    if self.lights[d][action]["timer"] < 0:
                        self.lights[d][action]["timer"] = 0

    def apply_command(self, lanes_data):
        # Cập nhật trạng thái đèn từ MQTT payload
        for lane_cmd in lanes_data:
            lane_id = lane_cmd.get("lane_id")
            if lane_id in self.lane_to_dir:
                d = self.lane_to_dir[lane_id]
                if "straight" in lane_cmd:
                    self.lights[d]["straight"]["state"] = lane_cmd["straight"].get("state", "red")
                    self.lights[d]["straight"]["timer"] = lane_cmd["straight"].get("duration", 0)
                if "left" in lane_cmd:
                    self.lights[d]["left"]["state"] = lane_cmd["left"].get("state", "red")
                    self.lights[d]["left"]["timer"] = lane_cmd["left"].get("duration", 0)

    def is_allowed(self, direction, turn_intention):
        # Quy tắc đặc biệt: rẽ phải luôn được phép (mô phỏng luồng tách riêng/slip lane).
        if turn_intention == "RIGHT":
            return True

        # Chuẩn hóa intention lạ về STRAIGHT để tránh lỗi do dữ liệu bẩn.
        if turn_intention not in ["STRAIGHT", "LEFT", "RIGHT"]:
            turn_intention = "STRAIGHT"

        # Check trạng thái đèn theo direction và action
        action = "left" if turn_intention == "LEFT" else "straight"
        
        # Chỉ đi khi đèn xanh
        return self.lights[direction][action]["state"] == "green"

    def get_display_mode_for_direction(self, direction):
        # Trả về dict trạng thái đèn để renderer vẽ
        if direction not in self.lights:
            return {"straight": "red", "left": "red"}
        
        return {
            "straight": self.lights[direction]["straight"]["state"],
            "left": self.lights[direction]["left"]["state"]
        }
