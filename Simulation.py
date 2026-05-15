"""
Lớp điều phối mô phỏng cấp cao.

File này không xử lý chi tiết hành vi xe hay logic đèn,
mà chỉ gọi đúng thứ tự giữa các module chuyên trách.
"""

import pygame
import os

from traffic_light_logic import Intersection
from traffic_light_renderer import draw_traffic_signals
from control_light import ControlLightFileReader
from control_vehicle import VehicleController
from road_layout import draw_roads_and_islands, get_intersection_points


class SimulationMap:
    # File này chỉ điều phối các module: hạ tầng đường, điều khiển xe, điều khiển đèn.
    def __init__(self):
        # Duyệt toàn bộ cặp tọa độ (x, y) do road_layout sinh ra để tạo nút giao tương ứng.
        # Vòng for trong list comprehension đảm bảo mỗi giao điểm đều có một Intersection độc lập.
        self.intersections = [Intersection(x, y) for x, y in get_intersection_points()]
        if hasattr(Intersection, "set_layout_positions"):
            Intersection.set_layout_positions([(ic.cx, ic.cy) for ic in self.intersections])

        # Danh sách phương tiện dùng chung cho cả controller và bước vẽ.
        self.vehicles = []

        # VehicleController thao tác trực tiếp trên self.vehicles và đọc trạng thái đèn qua self.intersections.
        self.vehicle_controller = VehicleController(self.intersections, self.vehicles)

        # Doc file output_control_light.json de cap nhat trang thai den.
        self.light_reader = ControlLightFileReader()

        # Load ArUco markers (0: top-left, 1: top-right, 2: bottom-left, 3: bottom-right)
        self.markers = []
        for i in range(4):
            path = os.path.join("aruco marker", f"4x4_1000-{i}.svg")
            try:
                self.markers.append(pygame.image.load(path))
            except Exception as e:
                print(f"Lỗi load marker {path}: {e}")
                self.markers.append(None)

    def update(self, dt):
        # 0) Doc trang thai den tu file output (server).
        self.light_reader.update_intersections(self.intersections)

        # 1) Cap nhat xe theo trang thai den da doc.
        self.vehicle_controller.update(dt)

    def _draw_aruco_markers(self, surface):
        # Vẽ 4 ArUco markers để nhận diện và canh lề 4 góc.
        screen_w, screen_h = surface.get_size()

        # Kích thước marker tự co giãn theo màn hình
        marker_size = max(40, min(100, int(min(screen_w, screen_h) * 0.08)))
        quiet = 5
        margin = max(10, quiet + 4)

        # Tọa độ 4 góc (phải khớp thứ tự 0,1,2,3 lúc load)
        # 0: Top-Left, 1: Top-Right, 2: Bottom-Left, 3: Bottom-Right
        positions = [
            (margin, margin),
            (screen_w - margin - marker_size, margin),
            (margin, screen_h - margin - marker_size),
            (screen_w - margin - marker_size, screen_h - margin - marker_size)
        ]

        if not hasattr(self, 'markers'):
            return

        for img, (px, py) in zip(self.markers, positions):
            if img is None:
                continue
            
            # Draw quiet zone (white margin)
            pygame.draw.rect(surface, (255, 255, 255), (px - quiet, py - quiet, marker_size + 2 * quiet, marker_size + 2 * quiet))
            
            # Scale and draw marker
            scaled_img = pygame.transform.smoothscale(img, (marker_size, marker_size))
            surface.blit(scaled_img, (px, py))

    def draw(self, surface):
        # Vẽ nền hạ tầng trước để các lớp sau (xe, đèn) đè lên đúng thứ tự thị giác.
        draw_roads_and_islands(surface, self.intersections)

        # Duyệt từng xe để vẽ theo vị trí/góc hiện thời trong frame.
        for v in self.vehicles:
            v.draw(surface)

        # Vẽ đèn sau cùng để luôn dễ quan sát kể cả khi có xe đi gần cột đèn.
        draw_traffic_signals(surface, self.intersections)

        # Vẽ marker hiệu chuẩn trên cùng để luôn rõ ràng cho camera.
        self._draw_aruco_markers(surface)