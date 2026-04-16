"""
Lớp điều phối mô phỏng cấp cao.

File này không xử lý chi tiết hành vi xe hay logic đèn,
mà chỉ gọi đúng thứ tự giữa các module chuyên trách.
"""

import pygame

from traffic_light_logic import Intersection
from traffic_light_renderer import draw_traffic_signals
from control_vehicle import VehicleController
from road_layout import draw_roads_and_islands, get_intersection_points


class SimulationMap:
    # File này chỉ điều phối các module: hạ tầng đường, điều khiển xe, điều khiển đèn.
    def __init__(self):
        # Duyệt toàn bộ cặp tọa độ (x, y) do road_layout sinh ra để tạo nút giao tương ứng.
        # Vòng for trong list comprehension đảm bảo mỗi giao điểm đều có một Intersection độc lập.
        self.intersections = [Intersection(x, y) for x, y in get_intersection_points()]

        # Danh sách phương tiện dùng chung cho cả controller và bước vẽ.
        self.vehicles = []

        # VehicleController thao tác trực tiếp trên self.vehicles và đọc trạng thái đèn qua self.intersections.
        self.vehicle_controller = VehicleController(self.intersections, self.vehicles)

    def update(self, dt):
        # 1) Cập nhật xe trước để thu thập waiting_counts mới cho mỗi giao lộ.
        self.vehicle_controller.update(dt)

        # 2) Sau khi đã biết số xe chờ, cập nhật thời gian/pha đèn cho từng giao lộ.
        # Vòng for này giúp mỗi nút giao tự tiến hóa độc lập theo mật độ chờ cục bộ của chính nó.
        for ic in self.intersections:
            ic.update(dt)

    def _draw_qr_corner_markers(self, surface):
        # Vẽ 4 marker kiểu finder-pattern của QR để camera nhận diện biên màn hình.
        screen_w, screen_h = surface.get_size()

        # Kích thước marker tự co giãn theo màn hình, có giới hạn min/max để luôn dễ nhận.
        outer = max(34, min(78, int(min(screen_w, screen_h) * 0.065)))
        ring = max(6, outer // 5)
        quiet = max(5, ring)
        margin = max(10, quiet + 4)

        def draw_finder(x, y):
            # Quiet zone trắng quanh marker giúp camera tách khối tốt hơn.
            pygame.draw.rect(surface, (255, 255, 255), (x - quiet, y - quiet, outer + 2 * quiet, outer + 2 * quiet))

            # 3 lớp vuông QR: đen ngoài, trắng giữa, đen trong.
            pygame.draw.rect(surface, (0, 0, 0), (x, y, outer, outer))
            pygame.draw.rect(surface, (255, 255, 255), (x + ring, y + ring, outer - 2 * ring, outer - 2 * ring))
            pygame.draw.rect(surface, (0, 0, 0), (x + 2 * ring, y + 2 * ring, outer - 4 * ring, outer - 4 * ring))

        # Tọa độ 4 góc trong khung nhìn.
        tl = (margin, margin)
        tr = (screen_w - margin - outer, margin)
        bl = (margin, screen_h - margin - outer)
        br = (screen_w - margin - outer, screen_h - margin - outer)

        for px, py in (tl, tr, bl, br):
            draw_finder(px, py)

    def draw(self, surface):
        # Vẽ nền hạ tầng trước để các lớp sau (xe, đèn) đè lên đúng thứ tự thị giác.
        draw_roads_and_islands(surface, self.intersections)

        # Duyệt từng xe để vẽ theo vị trí/góc hiện thời trong frame.
        for v in self.vehicles:
            v.draw(surface)

        # Vẽ đèn sau cùng để luôn dễ quan sát kể cả khi có xe đi gần cột đèn.
        draw_traffic_signals(surface, self.intersections)

        # Vẽ marker hiệu chuẩn trên cùng để luôn rõ ràng cho camera.
        self._draw_qr_corner_markers(surface)