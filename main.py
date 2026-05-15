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
from datetime import datetime
from config import (
    BG_COLOR,
    FULLSCREEN_ENABLED,
    DEFAULT_SCREEN_WIDTH,
    DEFAULT_SCREEN_HEIGHT,
    R,
    STOP_LINE_DIST,
    NORTH,
    SOUTH,
    EAST,
    WEST,
)
from road_layout import configure_layout
from Simulation import SimulationMap


def _get_local_time_str():
    # Lấy thời gian thực từ máy để hiển thị/log.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _build_control_light_header(lane_total=16):
    # Header cố định cho file input_control_light.txt.
    fields = ["Frame", "Time"]
    for i in range(lane_total):
        fields.append(f"Lane_{i}_Cars")
        fields.append(f"Lane_{i}_Bikes")
    return ",".join(fields)


def _build_control_light_row(frame_index, time_str, lane_counts, lane_total=16):
    # Chuyển dữ liệu đếm xe sang một dòng CSV.
    values = [str(frame_index), time_str]
    for i in range(lane_total):
        if i < len(lane_counts):
            cars, bikes = lane_counts[i]
        else:
            cars, bikes = 0, 0
        values.append(str(cars))
        values.append(str(bikes))
    return ",".join(values)


def _write_control_light_file(file_path, header, rows):
    # Ghi đè file theo chu kỳ; giữ format dễ parse.
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")


def draw_demo_wait_stats_overlay(surface, stats, font, time_str):
    # Demo kiểm tra nhanh: xóa hàm này sau khi xong trình diễn.
    lines = [f"time: {time_str}"]

    if stats and stats.get("count", 0) > 0:
        lines += [
            f"Red wait count: {stats['count']}",
            f"avg: {stats['avg']:.2f}s  median: {stats['median']:.2f}s",
            f"min: {stats['min']:.2f}s  max: {stats['max']:.2f}s",
        ]
    else:
        lines.append("Red wait: no data")

    padding = 8
    line_h = font.get_linesize()
    width = max(font.size(line)[0] for line in lines) + padding * 2
    height = line_h * len(lines) + padding * 2

    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    panel.fill((0, 0, 0, 140))

    y = padding
    for line in lines:
        text = font.render(line, True, (255, 255, 255))
        panel.blit(text, (padding, y))
        y += line_h

    surface.blit(panel, (10, 10))


def draw_demo_lane_indices(surface, intersections, controller, font):
    # Demo: ve so lane nho o giua duong (xoa khi demo xong).
    lane_offset = int(R * 0.55)
    along_offset = 16

    for ic in intersections:
        for direction in (EAST, WEST, SOUTH, NORTH):
            lane_number = controller.get_lane_number_for_intersection(ic, direction)
            if lane_number is None:
                continue

            label = str(lane_number)
            text = font.render(label, True, (255, 255, 255))
            tw, th = text.get_size()

            if direction == EAST:
                base_x = ic.cx - STOP_LINE_DIST - along_offset
                base_y = ic.cy + lane_offset
            elif direction == WEST:
                base_x = ic.cx + STOP_LINE_DIST + along_offset
                base_y = ic.cy - lane_offset
            elif direction == SOUTH:
                base_x = ic.cx - lane_offset
                base_y = ic.cy - STOP_LINE_DIST - along_offset
            else:
                base_x = ic.cx + lane_offset
                base_y = ic.cy + STOP_LINE_DIST + along_offset

            x = base_x - tw / 2
            y = base_y - th / 2
            surface.blit(text, (int(x), int(y)))


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

    # Demo: thống kê chờ đèn đỏ và in console định kỳ.
    debug_font = pygame.font.Font(None, 22)
    lane_font = pygame.font.Font(None, 16)
    stats_print_interval = 3.0
    stats_print_timer = 0.0
    last_stats = {"count": 0, "avg": 0.0, "median": 0.0, "min": 0.0, "max": 0.0}
    frame_index = 0

    # Demo: ghi file input_control_light.txt theo chu kỳ 5s.
    control_light_path = "input_control_light.txt"
    control_light_header = _build_control_light_header(lane_total=16)
    control_light_rows = []
    control_light_interval = 5.0
    control_light_timer = 0.0

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
        frame_index += 1

        # Demo: cập nhật thống kê theo thời gian thực cho overlay.
        last_stats = sim_map.vehicle_controller.get_red_wait_stats()
        now_str = _get_local_time_str()

        # Demo: cập nhật thống kê theo thời gian thực cho overlay.
        last_stats = sim_map.vehicle_controller.get_red_wait_stats()

        # Demo: in thống kê ra console mỗi vài giây.
        stats_print_timer += dt
        if stats_print_timer >= stats_print_interval:
            if last_stats["count"] > 0:
                print(
                    "[{time}] [red_wait] count={count} avg={avg:.2f}s median={median:.2f}s min={min:.2f}s max={max:.2f}s".format(
                        time=now_str,
                        **last_stats,
                    )
                )
            stats_print_timer = 0.0

        # Demo: cập nhật file đèn đỏ mỗi 5 giây và ghi đè.
        control_light_timer += dt
        if control_light_timer >= control_light_interval:
            lane_counts = sim_map.vehicle_controller.get_red_wait_lane_counts(lane_total=16)
            row = _build_control_light_row(frame_index, now_str, lane_counts, lane_total=16)
            control_light_rows.append(row)
            if len(control_light_rows) > 2:
                control_light_rows.pop(0)
            _write_control_light_file(control_light_path, control_light_header, control_light_rows)
            control_light_timer = 0.0

        # 2) Xóa frame cũ bằng màu nền.
        screen.fill(BG_COLOR)

        # 3) Vẽ frame mới (đường, xe, đèn).
        sim_map.draw(screen)

        # Demo: ve so lane (xoa dong nay khi khong can nua).
        draw_demo_lane_indices(screen, sim_map.intersections, sim_map.vehicle_controller, lane_font)

        # Demo: overlay thống kê (xóa dòng này khi không cần nữa).
        draw_demo_wait_stats_overlay(screen, last_stats, debug_font, now_str)

        # 4) Đẩy buffer lên màn hình để người dùng thấy frame vừa vẽ.
        pygame.display.flip()

    # Giải phóng tài nguyên pygame và kết thúc tiến trình Python.
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    # Chỉ chạy main khi file được chạy trực tiếp.
    main()