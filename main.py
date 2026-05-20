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

    font = pygame.font.SysFont(None, 24)
    screen_w = screen.get_width()
    total_width = 80 + 10 + 80 + 10 + 80 + 20 + 100
    start_x = (screen_w - total_width) // 2
    btn_pause = pygame.Rect(start_x, 10, 80, 30)
    btn_slower = pygame.Rect(start_x + 90, 10, 80, 30)
    btn_faster = pygame.Rect(start_x + 180, 10, 80, 30)
    sim_speed = 1.0
    is_paused = False

    running = True
    while running:
        # tick(60) giới hạn tốc độ vòng lặp; chia 1000 để đổi mili-giây sang giây.
        dt = clock.tick(60) / 1000.0

        # Quét toàn bộ sự kiện phát sinh trong frame hiện tại.
        for event in pygame.event.get():
            # Nếu người dùng bấm nút đóng cửa sổ thì thoát vòng lặp chính.
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if btn_pause.collidepoint(event.pos):
                        is_paused = not is_paused
                    elif btn_slower.collidepoint(event.pos):
                        sim_speed = max(0.25, sim_speed / 2.0)
                    elif btn_faster.collidepoint(event.pos):
                        sim_speed = min(8.0, sim_speed * 2.0)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    is_paused = not is_paused
                elif event.key == pygame.K_LEFT or event.key == pygame.K_DOWN:
                    sim_speed = max(0.25, sim_speed / 2.0)
                elif event.key == pygame.K_RIGHT or event.key == pygame.K_UP:
                    sim_speed = min(8.0, sim_speed * 2.0)

        # 1) Cập nhật trạng thái mô phỏng (xe, đèn) theo dt.
        if not is_paused:
            sim_map.update(dt * sim_speed)

        # 2) Xóa frame cũ bằng màu nền.
        screen.fill(BG_COLOR)

        # 3) Vẽ frame mới (đường, xe, đèn).
        sim_map.draw(screen)

        pygame.draw.rect(screen, (200, 200, 200), btn_pause)
        pause_text = font.render("Play" if is_paused else "Pause", True, (0, 0, 0))
        screen.blit(pause_text, (btn_pause.x + 10, btn_pause.y + 5))

        pygame.draw.rect(screen, (200, 200, 200), btn_slower)
        slower_text = font.render("Slower", True, (0, 0, 0))
        screen.blit(slower_text, (btn_slower.x + 10, btn_slower.y + 5))

        pygame.draw.rect(screen, (200, 200, 200), btn_faster)
        faster_text = font.render("Faster", True, (0, 0, 0))
        screen.blit(faster_text, (btn_faster.x + 10, btn_faster.y + 5))

        speed_text = font.render(f"Speed: {sim_speed}x", True, (0, 0, 0))
        screen.blit(speed_text, (start_x + 280, 15))

        # 4) Đẩy buffer lên màn hình để người dùng thấy frame vừa vẽ.
        pygame.display.flip()

    # Giải phóng tài nguyên pygame và kết thúc tiến trình Python.
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # Chỉ chạy main khi file được chạy trực tiếp.
    main()