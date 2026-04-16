# car_vehicle.py
import random
from vehicle import Vehicle


class Car(Vehicle):
    def __init__(self, direction, axis_pos):
        # Bước 1: dựng xe nền với toàn bộ cơ chế chung (di chuyển, cua, vẽ, trạng thái).
        super().__init__(direction, axis_pos)

        # Bước 2: ghi đè thông số hình học cho ô tô.
        # Ô tô chiếm diện tích lớn hơn nên yêu cầu khoảng trống an toàn lớn hơn trong luồng xe.
        self.width = 16
        self.length = 36

        # Màu hiển thị mặc định cho ô tô.
        self.color = (255, 50, 50)

        # Bước 3: lấy tốc độ ngẫu nhiên trong dải vận tốc của ô tô.
        # Dải này thấp hơn xe máy để tái hiện đặc tính tăng/giảm tốc của xe lớn.
        self.max_speed = random.uniform(40.0, 60.0)

        # Tốc độ hiện tại khởi tạo bằng max_speed và sẽ được controller điều chỉnh theo tình huống.
        self.current_speed = self.max_speed

        # Bước 4: spawn xe từ ngoài biên tuyến theo đúng hướng ban đầu.
        self.init_position()