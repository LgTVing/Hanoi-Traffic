# motor.py
import random
from vehicle import Vehicle


class Motorcycle(Vehicle):
    def __init__(self, direction, axis_pos):
        # Bước 1: khởi tạo toàn bộ thuộc tính nền (hướng, vị trí, trạng thái cua, góc hiển thị...).
        super().__init__(direction, axis_pos)

        # Bước 2: ghi đè hình học để phân biệt lớp phương tiện xe máy.
        # Thu nhỏ thêm bề ngang để cùng một làn có thể lọt 2 xe máy trong tình huống đông.
        self.width = 6
        self.length = 20

        # Màu hiển thị mặc định cho xe máy.
        self.color = (0, 255, 100)

        # Bước 3: gán tốc độ mục tiêu ngẫu nhiên trong dải xe máy.
        # random.uniform giúp mỗi xe có tính đa dạng, tránh dòng xe chạy đồng tốc tuyệt đối.
        self.max_speed = random.uniform(65.0, 90.0)

        # Tốc độ hiện tại khởi tạo bằng tốc độ tối đa (sẽ bị điều chỉnh dần trong update).
        self.current_speed = self.max_speed

        # Bước 4: đặt xe ngoài biên để mô phỏng xe đi vào từ đầu tuyến.
        self.init_position()