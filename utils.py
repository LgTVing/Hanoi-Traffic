# utils.py
import pygame
import random
from config import *


def draw_rotated_rect(surface, color, x, y, width, length, angle):
    # Tạo một surface tạm có alpha để vẽ hình chữ nhật gốc theo trục đứng.
    # Làm vậy giúp xoay hình mượt hơn so với thao tác trực tiếp lên surface chính.
    rect_surface = pygame.Surface((width, length), pygame.SRCALPHA)

    # Vẽ thân xe (bo góc nhẹ để nhìn tự nhiên hơn).
    pygame.draw.rect(rect_surface, color, (0, 0, width, length), border_radius=3)

    # Xoay thân xe theo góc visual_angle hiện tại.
    rotated = pygame.transform.rotate(rect_surface, angle)

    # Căn hình xoay theo tâm (x, y) để vị trí xe không bị lệch khi đổi góc.
    rect = rotated.get_rect(center=(int(x), int(y)))

    # Chép hình đã xoay lên surface khung hình hiện tại.
    surface.blit(rotated, rect)


def get_target_offset(intention):
    # Ánh xạ ý định rẽ sang dải offset làn tương ứng.
    # if 1: xe có ý định rẽ trái -> ưu tiên vùng offset nhỏ (làn trong/trái).
    if intention == "LEFT":
        return random.uniform(10, 30)

    # elif: xe đi thẳng -> ưu tiên vùng giữa mặt cắt đường.
    elif intention == "STRAIGHT":
        return random.uniform(35, 55)

    # else: mặc định xem như rẽ phải -> vùng offset lớn (làn ngoài/phải).
    else:
        return random.uniform(65, 80)


def apply_offset(direction, offset, axis_pos):
    # Quy đổi từ (trục đường + offset làn) sang tọa độ tuyệt đối trên màn hình.
    # Mỗi hướng có quy ước dấu offset khác nhau để giữ cùng nghĩa "lệch trái/lệch phải" theo chiều chạy.

    if direction == SOUTH:
        return axis_pos - offset

    if direction == NORTH:
        return axis_pos + offset

    if direction == EAST:
        return axis_pos + offset

    if direction == WEST:
        return axis_pos - offset

    # Fallback phòng trường hợp direction không hợp lệ.
    return axis_pos