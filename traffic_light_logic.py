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
        # self.lane_mapping là ánh xạ: Hướng di chuyển (v.direction) -> Lane ID theo PROTOCOL.md
        # Xe đi hướng SOUTH (từ Bắc xuống Nam) -> Lane Bắc (N)
        # Xe đi hướng NORTH (từ Nam lên Bắc) -> Lane Nam (S)
        # Xe đi hướng EAST (từ Tây sang Đông) -> Lane Tây (W)
        # Xe đi hướng WEST (từ Đông sang Tây) -> Lane Đông (E)
        self.lane_mapping = {}
        if intersection_id == 0:
            self.lane_mapping = {SOUTH: 10, WEST: 3, NORTH: 9, EAST: 0}
        elif intersection_id == 1:
            self.lane_mapping = {SOUTH: 14, WEST: 2, NORTH: 13, EAST: 1}
        elif intersection_id == 2:
            self.lane_mapping = {SOUTH: 11, WEST: 7, NORTH: 8, EAST: 4}
        elif intersection_id == 3:
            self.lane_mapping = {SOUTH: 15, WEST: 6, NORTH: 12, EAST: 5}

        # Ánh xạ ngược từ lane_id sang hướng (direction)
        self.lane_to_dir = {v: k for k, v in self.lane_mapping.items()}

        # Trạng thái đèn của mỗi hướng (mặc định tất cả đều đỏ 20s)
        self.lights = {
            direction: {
                "straight": {"state": "red", "timer": 20.0},
                "left": {"state": "red", "timer": 20.0}
            } for direction in [NORTH, EAST, SOUTH, WEST]
        }

        # Khởi tạo đèn theo kịch bản: 2 hướng xanh, 2 hướng đỏ
        if intersection_id in [0, 3]:
            # Ngã tư 0, 3: Bắc Nam xanh, Đông Tây đỏ
            for d in [NORTH, SOUTH]:
                self.lights[d]["straight"]["state"] = "green"
                self.lights[d]["left"]["state"] = "green"
        elif intersection_id in [1, 2]:
            # Ngã tư 1, 2: Đông Tây xanh, Bắc Nam đỏ
            for d in [EAST, WEST]:
                self.lights[d]["straight"]["state"] = "green"
                self.lights[d]["left"]["state"] = "green"

        # Số xe chờ theo hướng (cập nhật từ VehicleController mỗi frame).
        self.waiting_counts = {NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0}

    def reset_to_default(self):
        for direction in [NORTH, EAST, SOUTH, WEST]:
            self.lights[direction]["straight"] = {"state": "red", "timer": 20.0}
            self.lights[direction]["left"] = {"state": "red", "timer": 20.0}

        if self.intersection_id in [0, 3]:
            for d in [NORTH, SOUTH]:
                self.lights[d]["straight"]["state"] = "green"
                self.lights[d]["left"]["state"] = "green"
        elif self.intersection_id in [1, 2]:
            for d in [EAST, WEST]:
                self.lights[d]["straight"]["state"] = "green"
                self.lights[d]["left"]["state"] = "green"

    def update(self, dt):
        # Trừ timer đếm ngược
        for d in self.lights:
            for action in ["straight", "left"]:
                if self.lights[d][action]["timer"] > 0:
                    self.lights[d][action]["timer"] -= dt
                
                # Hết thời gian mà chưa có lệnh mới: hoạt động như đèn bình thường (luân phiên 20s)
                if self.lights[d][action]["timer"] <= 0:
                    if self.lights[d][action]["state"] in ["green", "yellow"]:
                        self.lights[d][action]["state"] = "red"
                    else:
                        self.lights[d][action]["state"] = "green"
                    self.lights[d][action]["timer"] = 20.0

        """
        {
            "intersection_id": 1,
            "lanes": [
                {
                    "lane_id": 8,
                    "straight": {
                        "state": "red",
                        "duration": 1
                    },
                    "left": {
                        "state": "red",
                        "duration": 1
                    }
                },
        """

    def apply_command(self, lanes_data):
        # print("apply_command for intersection: ", self.intersection_id)
        # print("lanes data: ", lanes_data)
        # Cập nhật trạng thái đèn từ MQTT payload
        for lane_cmd in lanes_data:
            # print("lane_cmd: ", lane_cmd)
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
