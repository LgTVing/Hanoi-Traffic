"""
Điểm vào (entry point) của mô phỏng giao thông.

Luồng chạy chính:
1) Khởi tạo pygame và màn hình.
2) Đồng bộ bố cục hạ tầng theo kích thước màn hình.
3) Chạy game-loop: đọc sự kiện -> cập nhật logic -> vẽ frame.
4) Thoát an toàn khi người dùng đóng cửa sổ.
"""

import pygame
import sys
from config import BG_COLOR, FULLSCREEN_ENABLED, DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT
from road_layout import configure_layout
from Simulation import SimulationMap


def main():
    # Bắt buộc gọi init trước khi dùng display, time, event...
    pygame.init()

    # Nhánh 1: chạy fullscreen để phủ toàn bộ màn hình thật.
    if FULLSCREEN_ENABLED:
        # pygame.display.Info() trả thông tin độ phân giải hiện tại của hệ điều hành.
        info = pygame.display.Info()
        screen = pygame.display.set_mode((info.current_w, info.current_h), pygame.FULLSCREEN)
    # Nhánh 2: chạy theo kích thước cố định (phục vụ debug/ghi hình).
    else:
        screen = pygame.display.set_mode((DEFAULT_SCREEN_WIDTH, DEFAULT_SCREEN_HEIGHT))

    # Đồng bộ layout sau khi tạo cửa sổ để ROAD_BOUNDS/ROAD_X/Y bám đúng thực tế.
    configure_layout(*screen.get_size())

    pygame.display.set_caption("Hanoi Big Intersection - Modular Architecture")
    # Clock giữ nhịp tối đa 60 FPS và cung cấp dt để chuyển động độc lập FPS.
    clock = pygame.time.Clock()

    # Đối tượng điều phối toàn bộ map: danh sách giao lộ + phương tiện + bộ điều khiển.
    sim_map = SimulationMap()

    running = True
    while running:
        # tick(60) giới hạn tốc độ vòng lặp; chia 1000 để đổi mili-giây sang giây.
        dt = clock.tick(60) / 1000.0

        # Quét toàn bộ sự kiện phát sinh trong frame hiện tại.
        for event in pygame.event.get():
            # Nếu người dùng bấm nút đóng cửa sổ thì thoát vòng lặp chính.
            if event.type == pygame.QUIT:
                running = False

        # 1) Cập nhật trạng thái mô phỏng (xe, đèn) theo dt.
        sim_map.update(dt)

        # 2) Xóa frame cũ bằng màu nền.
        screen.fill(BG_COLOR)

        # 3) Vẽ frame mới (đường, xe, đèn).
        sim_map.draw(screen)

        # 4) Đẩy buffer lên màn hình để người dùng thấy frame vừa vẽ.
        pygame.display.flip()

    # Giải phóng tài nguyên pygame và kết thúc tiến trình Python.
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # Chỉ chạy main khi file được chạy trực tiếp.
    main()