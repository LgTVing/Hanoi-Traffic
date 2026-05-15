"""
Lớp điều phối mô phỏng cấp cao.

File này không xử lý chi tiết hành vi xe hay logic đèn,
mà chỉ gọi đúng thứ tự giữa các module chuyên trách.
"""

import pygame
import os

from traffic_light_logic import Intersection
from traffic_light_renderer import draw_traffic_signals
from control_vehicle import VehicleController
from road_layout import draw_roads_and_islands, get_intersection_points
import paho.mqtt.client as mqtt
import json


class SimulationMap:
    # File này chỉ điều phối các module: hạ tầng đường, điều khiển xe, điều khiển đèn.
    def __init__(self):
        # Duyệt toàn bộ cặp tọa độ (x, y) do road_layout sinh ra để tạo nút giao tương ứng.
        # Vòng for trong list comprehension đảm bảo mỗi giao điểm đều có một Intersection độc lập.
        self.intersections = []
        for i, (x, y) in enumerate(get_intersection_points()):
            self.intersections.append(Intersection(x, y, i))

        # Danh sách phương tiện dùng chung cho cả controller và bước vẽ.
        self.vehicles = []

        # VehicleController thao tác trực tiếp trên self.vehicles và đọc trạng thái đèn qua self.intersections.
        self.vehicle_controller = VehicleController(self.intersections, self.vehicles)

        # Load ArUco markers (0: top-left, 1: top-right, 2: bottom-left, 3: bottom-right)
        self.markers = []
        for i in range(4):
            path = os.path.join("aruco marker", f"4x4_1000-{i}.svg")
            try:
                self.markers.append(pygame.image.load(path))
            except Exception as e:
                print(f"Lỗi load marker {path}: {e}")
                self.markers.append(None)

        # Thiết lập MQTT để nhận tín hiệu điều khiển đèn
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_message = self.on_mqtt_message
        try:
            self.mqtt_client.connect("3.107.18.217", 1883)
            self.mqtt_client.subscribe("traffic/lights")
            self.mqtt_client.loop_start()
            print("Simulator subscribed to traffic/lights")
        except Exception as e:
            print(f"MQTT connect error in Simulator: {e}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            for ic_data in payload.get("intersections", []):
                ic_id = ic_data.get("intersection_id")
                if ic_id is not None and 0 <= ic_id < len(self.intersections):
                    self.intersections[ic_id].apply_command(ic_data.get("lanes", []))
        except Exception as e:
            print(f"MQTT msg process error: {e}")

    def update(self, dt):
        # 1) Cập nhật xe trước để thu thập waiting_counts mới cho mỗi giao lộ.
        self.vehicle_controller.update(dt)

        # 2) Sau khi đã biết số xe chờ, cập nhật thời gian/pha đèn cho từng giao lộ.
        # Vòng for này giúp mỗi nút giao tự tiến hóa độc lập theo mật độ chờ cục bộ của chính nó.
        for ic in self.intersections:
            ic.update(dt)

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