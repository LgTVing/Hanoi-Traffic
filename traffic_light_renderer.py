import math
import pygame

from config import *


def draw_traffic_signals(surface, intersections):
    # Vẽ cụm tín hiệu đèn theo mode hiện tại của từng nút giao.
    def _rotate_points(points, center, angle_rad):
        # Quay danh sách điểm quanh tâm để tái sử dụng cùng một shape cho nhiều hướng.
        cx, cy = center
        ca = math.cos(angle_rad)
        sa = math.sin(angle_rad)
        out = []

        # Vòng for biến đổi từng điểm theo ma trận quay 2D.
        for px, py in points:
            dx, dy = px - cx, py - cy
            rx = cx + dx * ca - dy * sa
            ry = cy + dx * sa + dy * ca
            out.append((int(rx), int(ry)))
        return out

    def _rotate_point(point, center, angle_rad):
        # Tiện ích quay một điểm đơn lẻ (dùng cho tâm chấm đỏ).
        return _rotate_points([point], center, angle_rad)[0]

    def _draw_rotated_housing(x, y, bw, bh, angle_rad):
        # Vẽ nền đen theo đúng góc quay để vỏ đèn luôn đồng bộ với hướng cụm đèn.
        box = [
            (x - bw / 2, y - bh / 2),
            (x + bw / 2, y - bh / 2),
            (x + bw / 2, y + bh / 2),
            (x - bw / 2, y + bh / 2),
        ]
        pygame.draw.polygon(surface, (20, 20, 20), _rotate_points(box, (x, y), angle_rad))

    def draw_signal(x, y, mode, angle_rad=0.0):
        # Vẽ vỏ hộp đèn 3 ngăn theo hàng ngang.
        # Khi quay theo angle_rad, chiều dài cụm sẽ luôn vuông góc hướng đường.
        bw, bh = 56, 24
        _draw_rotated_housing(x, y, bw, bh, angle_rad)

        # Mỗi cụm luôn có 3 đèn; màu từng đèn phản ánh quyền đi hiện tại của hướng đó.
        red_on = mode == "RED"
        straight_on = mode == "STRAIGHT"
        left_on = mode == "LEFT"

        # Bóng 1 (bên trái cụm): mũi tên rẽ trái kiểu <-.
        lx, ly = x - 16, y
        left_col = GREEN_ON if left_on else RED_ON
        left_poly = [
            (lx + 6, ly - 2),
            (lx - 1, ly - 2),
            (lx - 1, ly - 5),
            (lx - 8, ly),
            (lx - 1, ly + 5),
            (lx - 1, ly + 2),
            (lx + 6, ly + 2),
        ]
        pygame.draw.polygon(surface, left_col, _rotate_points(left_poly, (x, y), angle_rad))

        # Đèn mũi tên đi thẳng: xanh khi được đi thẳng, ngược lại hiển thị đỏ.
        # Bóng 2 (giữa cụm): mũi tên đi thẳng.
        sx, sy = x, y
        straight_col = GREEN_ON if straight_on else RED_ON
        shaft = [
            (sx - 2, sy + 5),
            (sx + 2, sy + 5),
            (sx + 2, sy - 1),
            (sx + 5, sy - 1),
            (sx, sy - 7),
            (sx - 5, sy - 1),
            (sx - 2, sy - 1),
        ]
        pygame.draw.polygon(surface, straight_col, _rotate_points(shaft, (x, y), angle_rad))

        # Bóng 3 (bên phải ngoài cùng): đèn đỏ chung.
        red_center = _rotate_point((x + 16, y), (x, y), angle_rad)
        pygame.draw.circle(surface, RED_ON if red_on else RED_OFF, red_center, 4)

    # Vòng for: mỗi giao lộ sẽ vẽ 4 cụm đèn (2 cho NS, 2 cho EW).
    for ic in intersections:
        # Dịch cụm đèn vào gần tâm giao lộ để dễ quan sát xe dừng trước vạch.
        inset_to_center = 18

        # Lấy mode hiển thị cho trục Bắc/Nam.
        mode_ns = ic.get_display_mode_for_direction(NORTH)

        # Đặt 2 đèn NS ở hai đầu stop line, quay icon để cùng hướng quan sát lái xe.
        draw_signal(ic.cx - 40, ic.cy - STOP_LINE_DIST + inset_to_center, mode_ns, angle_rad=math.pi)
        draw_signal(ic.cx + 40, ic.cy + STOP_LINE_DIST - inset_to_center, mode_ns, angle_rad=0.0)

        # Lấy mode hiển thị cho trục Đông/Tây.
        mode_ew = ic.get_display_mode_for_direction(EAST)

        # Đặt 2 đèn EW lệch phải theo chiều lưu thông hiện hành.
        draw_signal(ic.cx - STOP_LINE_DIST + inset_to_center, ic.cy + 40, mode_ew, angle_rad=math.pi / 2)
        draw_signal(ic.cx + STOP_LINE_DIST - inset_to_center, ic.cy - 40, mode_ew, angle_rad=-math.pi / 2)
