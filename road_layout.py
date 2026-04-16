"""
Module hạ tầng giao thông.

Nhiệm vụ chính:
1) Quản lý cấu trúc làn đường và lưới giao lộ.
2) Quy đổi offset làn <-> tọa độ tuyệt đối.
3) Cung cấp API spawn/cleanup theo biên hạ tầng.
4) Vẽ mặt đường, vạch và đảo giao thông.
"""

import pygame

from config import *

# Hệ làn đường dùng chung cho điều khiển xe và hiển thị.
LANES = [16, 42, 68, 94]
LANE_INTENTIONS = {
    "LEFT": [16, 42],
    # Giữ 1 làn dùng chung trái+thẳng (42) và 1 làn thẳng thuần (68).
    "STRAIGHT": [42, 68],
    "RIGHT": [94],
}

# Trục đường theo 2 phương. Sẽ được tính bởi configure_layout().
ROAD_X_POSITIONS = []
ROAD_Y_POSITIONS = []

# Biên hạ tầng giao thông (đầu/cuối đường) dùng cho vẽ, spawn và dọn xe.
# Mặc định bám theo cửa sổ nhưng có thể thay đổi độc lập nếu muốn kéo dài/thu ngắn hạ tầng.
ROAD_BOUNDS = {
    "min_x": 0,
    "max_x": WINDOW_SIZE,
    "min_y": 0,
    "max_y": WINDOW_SIZE,
}

SPAWN_PADDING = 50
CLEANUP_PADDING = 200


def _distribute_positions(start, end, count):
    # Chia đều count vị trí trong đoạn [start, end].
    # if: chỉ cần 1 điểm thì lấy trung điểm để vẫn hợp lệ về mặt hình học.
    if count <= 1:
        return [int(round((start + end) / 2))]

    # if: chuẩn hóa đầu-cuối để luôn có start <= end trước khi tính bước.
    if end < start:
        start, end = end, start

    # Khoảng cách đều giữa 2 trục liên tiếp.
    step = (end - start) / (count - 1)

    # Vòng for tạo danh sách vị trí [start, start+step, ..., end].
    return [int(round(start + i * step)) for i in range(count)]


def _effective_edge_margin(span):
    # Tính lề hợp lý để vẫn thấy vùng dừng đèn + vùng rẽ gần biên.
    desired = max(INTERSECTION_EDGE_MARGIN, BRANCH_D + 90, STOP_LINE_DIST + 130)
    max_allowed = max(R + 20, span // 2 - 120)

    # Kẹp giá trị lề trong [R+20, max_allowed] để tránh lề quá nhỏ hoặc quá lớn.
    return max(R + 20, min(desired, max_allowed))


def configure_layout(screen_width, screen_height):
    # Cập nhật biên hạ tầng và vị trí trục theo kích thước màn hình thực tế.
    ROAD_BOUNDS["min_x"] = 0
    ROAD_BOUNDS["max_x"] = int(screen_width)
    ROAD_BOUNDS["min_y"] = 0
    ROAD_BOUNDS["max_y"] = int(screen_height)

    # if: người dùng cung cấp sẵn list trục X -> ưu tiên dùng trực tiếp.
    if CUSTOM_ROAD_X_POSITIONS:
        ROAD_X_POSITIONS[:] = [int(x) for x in CUSTOM_ROAD_X_POSITIONS]
    # else: tự sinh trục X theo số cột và lề biên.
    else:
        margin_x = _effective_edge_margin(int(screen_width))
        ROAD_X_POSITIONS[:] = _distribute_positions(margin_x, int(screen_width) - margin_x, INTERSECTION_COLS)

    # if: người dùng cung cấp sẵn list trục Y -> ưu tiên dùng trực tiếp.
    if CUSTOM_ROAD_Y_POSITIONS:
        ROAD_Y_POSITIONS[:] = [int(y) for y in CUSTOM_ROAD_Y_POSITIONS]
    # else: tự sinh trục Y theo số hàng và lề biên.
    else:
        margin_y = _effective_edge_margin(int(screen_height))
        ROAD_Y_POSITIONS[:] = _distribute_positions(margin_y, int(screen_height) - margin_y, INTERSECTION_ROWS)


def apply_offset(direction, offset, axis_pos):
    # Quy đổi offset làn thành tọa độ tuyệt đối theo chiều chạy.
    # Các nhánh if giữ quy ước trái/phải nhất quán theo hướng tiến của phương tiện.
    if direction == SOUTH:
        return axis_pos - offset
    if direction == NORTH:
        return axis_pos + offset
    if direction == EAST:
        return axis_pos + offset
    if direction == WEST:
        return axis_pos - offset

    # Fallback nếu direction không hợp lệ.
    return axis_pos


def get_intersection_points():
    # Tạo danh sách giao lộ từ lưới trục X/Y hiện tại của hạ tầng.
    return [(x, y) for x in ROAD_X_POSITIONS for y in ROAD_Y_POSITIONS]


def get_axis_positions_for_direction(direction):
    # Xe đi theo trục dọc dùng ROAD_X, xe đi theo trục ngang dùng ROAD_Y.
    # if: NORTH/SOUTH chạy theo cột X cố định.
    if direction in [NORTH, SOUTH]:
        return ROAD_X_POSITIONS
    # else: EAST/WEST chạy theo hàng Y cố định.
    return ROAD_Y_POSITIONS


def get_nearest_axis_position(direction, reference_value):
    # Lấy trục gần nhất của hướng đích để xe rẽ nhập đúng vào đường đang tồn tại.
    axes = get_axis_positions_for_direction(direction)

    # if: không có trục (trường hợp cấu hình lỗi) thì trả về mốc tham chiếu để tránh crash.
    if not axes:
        return int(reference_value)

    # Chọn phần tử có độ lệch tuyệt đối nhỏ nhất.
    return min(axes, key=lambda v: abs(v - reference_value))


def get_spawn_position(direction, axis_pos, offset, padding=SPAWN_PADDING):
    # Spawn luôn từ đầu đường theo biên hạ tầng, không phụ thuộc trực tiếp WINDOW_SIZE.
    # Mỗi nhánh if trả một cặp (x, y) nằm ngoài biên theo đúng chiều xe sẽ đi vào.
    if direction == SOUTH:
        return apply_offset(SOUTH, offset, axis_pos), ROAD_BOUNDS["min_y"] - padding
    if direction == NORTH:
        return apply_offset(NORTH, offset, axis_pos), ROAD_BOUNDS["max_y"] + padding
    if direction == EAST:
        return ROAD_BOUNDS["min_x"] - padding, apply_offset(EAST, offset, axis_pos)
    if direction == WEST:
        return ROAD_BOUNDS["max_x"] + padding, apply_offset(WEST, offset, axis_pos)

    # Fallback an toàn cho direction không hợp lệ.
    return 0.0, 0.0


def is_inside_cleanup_bounds(x, y, padding=CLEANUP_PADDING):
    # Xe ra khỏi vùng đệm quanh hạ tầng thì được loại khỏi mô phỏng.
    # Điều kiện AND đảm bảo xe chỉ bị xóa khi vượt biên theo bất kỳ trục nào quá xa.
    return (
        ROAD_BOUNDS["min_x"] - padding <= x <= ROAD_BOUNDS["max_x"] + padding
        and ROAD_BOUNDS["min_y"] - padding <= y <= ROAD_BOUNDS["max_y"] + padding
    )


# Khởi tạo layout mặc định để module dùng được ngay cả khi chưa gọi configure_layout().
configure_layout(WINDOW_SIZE, WINDOW_SIZE)


def draw_roads_and_islands(surface, intersections):
    # Chỉ hiển thị nền hạ tầng (mặt đường + vạch + đảo), không can thiệp logic đèn/xe.
    def _bezier_quad(p0, p1, p2, steps=18):
        # Sinh dãy điểm trên đường cong Bezier bậc 2 để bo góc mềm.
        pts = []

        # Vòng for chạy từ 0..steps để lấy mẫu đều theo tham số t.
        for i in range(steps + 1):
            t = i / steps
            u = 1 - t
            x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
            y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
            pts.append((int(x), int(y)))
        return pts

    min_x = ROAD_BOUNDS["min_x"]
    max_x = ROAD_BOUNDS["max_x"]
    min_y = ROAD_BOUNDS["min_y"]
    max_y = ROAD_BOUNDS["max_y"]
    span_x = max_x - min_x
    span_y = max_y - min_y

    # Vòng for 1: duyệt từng trục dọc để vẽ các đại lộ theo phương Y.
    for x in ROAD_X_POSITIONS:
        # Vẽ trục đường dọc theo biên hạ tầng hiện tại.
        pygame.draw.rect(surface, ROAD_COLOR, (x - R, min_y, ROAD_WIDTH, span_y))

        # Vòng for 2: vẽ vạch tim dọc đứt đoạn cách nhau 30 px.
        for i in range(min_y, max_y, 30):
            pygame.draw.rect(surface, LINE_COLOR, (x - 1, i, 2, 15))

        # Vòng for 3: duyệt các lane offset để vẽ vạch phân làn phụ.
        for lane_off in LANES[:-1]:
            # Vòng for 4: lặp theo chiều dọc để tạo nét đứt trên từng lane.
            for i in range(min_y, max_y, 40):
                pygame.draw.rect(surface, (100, 100, 100), (x + lane_off + 13, i, 2, 20))
                pygame.draw.rect(surface, (100, 100, 100), (x - lane_off - 13, i, 2, 20))

    # Vòng for 1 (nhóm ngang): duyệt từng trục ngang để vẽ các đại lộ theo phương X.
    for y in ROAD_Y_POSITIONS:
        # Vẽ trục đường ngang theo biên hạ tầng hiện tại.
        pygame.draw.rect(surface, ROAD_COLOR, (min_x, y - R, span_x, ROAD_WIDTH))

        # Vòng for 2: vạch tim ngang đứt đoạn cách nhau 30 px.
        for i in range(min_x, max_x, 30):
            pygame.draw.rect(surface, LINE_COLOR, (i, y - 1, 15, 2))

        # Vòng for 3: duyệt offset lane để vẽ các vạch phân làn ngang.
        for lane_off in LANES[:-1]:
            # Vòng for 4: lặp theo phương X để tạo nét đứt theo từng lane.
            for i in range(min_x, max_x, 40):
                pygame.draw.rect(surface, (100, 100, 100), (i, y + lane_off + 13, 20, 2))
                pygame.draw.rect(surface, (100, 100, 100), (i, y - lane_off - 13, 20, 2))

    # Vòng for cuối: với mỗi giao lộ, vẽ 4 góc slip lane + 4 đảo dẫn hướng tương ứng.
    for ic in intersections:
        # Mỗi góc giao lộ gồm nhánh slip lane và một đảo dẫn hướng.
        A = (ic.cx - SLIP_START, ic.cy - BRANCH_D)
        B = (ic.cx - SLIP_OUT, ic.cy - BRANCH_D)
        C = (ic.cx - BRANCH_D, ic.cy - SLIP_OUT)
        D = (ic.cx - BRANCH_D, ic.cy - SLIP_START)
        corner_tl = (ic.cx - R, ic.cy - R)
        poly_tl = [A, B, C, D] + list(reversed(_bezier_quad(A, corner_tl, D, steps=20)))[1:-1]
        pygame.draw.polygon(surface, ROAD_COLOR, poly_tl)

        leg_v_tl = (ic.cx - R, ic.cy - BRANCH_D)
        leg_h_tl = (ic.cx - BRANCH_D, ic.cy - R)
        isl_tl = [corner_tl, leg_v_tl] + _bezier_quad(leg_v_tl, corner_tl, leg_h_tl, steps=28) + [leg_h_tl]
        pygame.draw.polygon(surface, ISLAND_COLOR, isl_tl)
        pygame.draw.polygon(surface, KERB_COLOR, isl_tl, 2)

        A = (ic.cx + SLIP_START, ic.cy - BRANCH_D)
        B = (ic.cx + SLIP_OUT, ic.cy - BRANCH_D)
        C = (ic.cx + BRANCH_D, ic.cy - SLIP_OUT)
        D = (ic.cx + BRANCH_D, ic.cy - SLIP_START)
        corner_tr = (ic.cx + R, ic.cy - R)
        poly_tr = [A, B, C, D] + list(reversed(_bezier_quad(A, corner_tr, D, steps=20)))[1:-1]
        pygame.draw.polygon(surface, ROAD_COLOR, poly_tr)

        leg_v_tr = (ic.cx + R, ic.cy - BRANCH_D)
        leg_h_tr = (ic.cx + BRANCH_D, ic.cy - R)
        isl_tr = [corner_tr, leg_v_tr] + _bezier_quad(leg_v_tr, corner_tr, leg_h_tr, steps=28) + [leg_h_tr]
        pygame.draw.polygon(surface, ISLAND_COLOR, isl_tr)
        pygame.draw.polygon(surface, KERB_COLOR, isl_tr, 2)

        A = (ic.cx + SLIP_START, ic.cy + BRANCH_D)
        B = (ic.cx + SLIP_OUT, ic.cy + BRANCH_D)
        C = (ic.cx + BRANCH_D, ic.cy + SLIP_OUT)
        D = (ic.cx + BRANCH_D, ic.cy + SLIP_START)
        corner_br = (ic.cx + R, ic.cy + R)
        poly_br = [A, B, C, D] + list(reversed(_bezier_quad(A, corner_br, D, steps=20)))[1:-1]
        pygame.draw.polygon(surface, ROAD_COLOR, poly_br)

        leg_v_br = (ic.cx + R, ic.cy + BRANCH_D)
        leg_h_br = (ic.cx + BRANCH_D, ic.cy + R)
        isl_br = [corner_br, leg_v_br] + _bezier_quad(leg_v_br, corner_br, leg_h_br, steps=28) + [leg_h_br]
        pygame.draw.polygon(surface, ISLAND_COLOR, isl_br)
        pygame.draw.polygon(surface, KERB_COLOR, isl_br, 2)

        A = (ic.cx - SLIP_START, ic.cy + BRANCH_D)
        B = (ic.cx - SLIP_OUT, ic.cy + BRANCH_D)
        C = (ic.cx - BRANCH_D, ic.cy + SLIP_OUT)
        D = (ic.cx - BRANCH_D, ic.cy + SLIP_START)
        corner_bl = (ic.cx - R, ic.cy + R)
        poly_bl = [A, B, C, D] + list(reversed(_bezier_quad(A, corner_bl, D, steps=20)))[1:-1]
        pygame.draw.polygon(surface, ROAD_COLOR, poly_bl)

        leg_v_bl = (ic.cx - R, ic.cy + BRANCH_D)
        leg_h_bl = (ic.cx - BRANCH_D, ic.cy + R)
        isl_bl = [corner_bl, leg_v_bl] + _bezier_quad(leg_v_bl, corner_bl, leg_h_bl, steps=28) + [leg_h_bl]
        pygame.draw.polygon(surface, ISLAND_COLOR, isl_bl)
        pygame.draw.polygon(surface, KERB_COLOR, isl_bl, 2)