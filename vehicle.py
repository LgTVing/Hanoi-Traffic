"""
Mô hình phương tiện cơ sở.

Lớp Vehicle định nghĩa:
- Trạng thái động học cơ bản (vị trí, tốc độ, hướng).
- Cơ chế đổi làn (offset -> target_offset).
- Cơ chế rẽ theo đường cong Bezier.
- Cách vẽ xe và xi-nhan.
"""

# vehicle.py
import pygame
import random
import math
from config import *
from utils import get_target_offset, apply_offset, draw_rotated_rect


class Vehicle:
    def __init__(self, direction, axis_pos):
        # Thuộc tính định danh theo hướng chạy và trục đường xe đang bám.
        self.direction = direction
        self.axis_pos = axis_pos

        # Kích thước và trạng thái cơ bản của thân xe.
        self.width = 10;
        self.length = 20;
        self.color = WHITE
        self.max_speed = 50.0;
        self.current_speed = 50.0
        self.x = 0.0;
        self.y = 0.0

        # offset: vị trí ngang hiện tại trong mặt cắt đường.
        # target_offset: vị trí ngang mục tiêu khi đổi làn.
        self.offset = 0.0;
        self.target_offset = 0.0
        self.is_waiting = False;
        self.is_stopping_for_light = False

        # Thời điểm bắt đầu dừng đèn đỏ (giây mô phỏng).
        # None nghĩa là xe hiện không trong trạng thái chờ đèn đỏ.
        self.red_wait_start_time = None
        # Thời gian chờ đèn đỏ gần nhất để debug nhanh nếu cần.
        self.red_wait_last = None

        # Ý định rẽ ban đầu của xe.
        # Lưu ý: controller có thể gán lại ý định khi xe tiến gần giao lộ kế tiếp.
        # Tỷ lệ lấy từ config để đồng bộ giữa các module.
        self.turn_intention = random.choices(TURN_INTENTION_OPTIONS, weights=TURN_INTENTION_WEIGHTS)[0]

        # Cờ trạng thái cua.
        self.has_turned = False
        self.is_turning = False

        # turn_t: tham số đường cong Bezier trong khoảng [0, 1].
        self.turn_t = 0.0

        # Bộ 3 điểm điều khiển của quỹ đạo cua Bezier.
        self.P0 = (0, 0);
        self.P1 = (0, 0);
        self.P2 = (0, 0)

        # curve_length dùng để đổi vận tốc thực sang tốc độ tăng turn_t.
        self.curve_length = 1.0;

        # Trạng thái đích sau khi hoàn tất cua.
        self.new_dir = direction
        self.new_axis_pos = axis_pos

        # Góc mặc định theo từng hướng để xe luôn quay đúng chiều chạy.
        self.angles = {NORTH: 0, WEST: 90, SOUTH: 180, EAST: 270}
        self.visual_angle = self.angles[self.direction]

    def init_position(self):
        # Chọn làn ban đầu theo ý định, rồi đặt xe tại mép ngoài màn hình.
        self.target_offset = get_target_offset(self.turn_intention)
        self.offset = self.target_offset

        # if/elif: mỗi hướng sẽ spawn ở phía ngoài biên tương ứng để xe đi vào khung nhìn.
        if self.direction == SOUTH:
            self.x = apply_offset(SOUTH, self.offset, self.axis_pos); self.y = -50.0
        elif self.direction == NORTH:
            self.x = apply_offset(NORTH, self.offset, self.axis_pos); self.y = WINDOW_SIZE + 50.0
        elif self.direction == EAST:
            self.y = apply_offset(EAST, self.offset, self.axis_pos); self.x = -50.0
        elif self.direction == WEST:
            self.y = apply_offset(WEST, self.offset, self.axis_pos); self.x = WINDOW_SIZE + 50.0

    def get_pos_1d(self):
        # Trả về tọa độ dọc theo trục chuyển động để so khoảng cách trước/sau.
        # if: xe chạy dọc thì dùng y làm tọa độ thứ tự.
        if self.direction in [SOUTH, NORTH]: return self.y
        # else: xe chạy ngang thì dùng x.
        return self.x

    def start_turn(self, P0, P1, P2, new_dir, new_offset, new_axis_pos=None):
        # Bắt đầu quỹ đạo rẽ Bezier với 3 điểm điều khiển.
        self.is_turning = True;
        self.turn_t = 0.0
        self.P0 = P0;
        self.P1 = P1;
        self.P2 = P2
        self.new_dir = new_dir;
        self.target_offset = new_offset

        # if/else: nếu controller không truyền new_axis_pos thì giữ trục cũ,
        # ngược lại cập nhật trục đích để khi kết thúc cua xe nhập đúng luồng mới.
        if new_axis_pos is None:
            self.new_axis_pos = self.axis_pos
        else:
            self.new_axis_pos = new_axis_pos

        # Ước lượng chiều dài cung để đổi tốc độ thực thành biến t (0 -> 1).
        d1 = math.hypot(P1[0] - P0[0], P1[1] - P0[1])
        d2 = math.hypot(P2[0] - P1[0], P2[1] - P1[1])
        self.curve_length = (d1 + d2) * 0.75

    def update_position(self, dt):
        # if lớn 1: xe đang ở trạng thái cua theo Bezier.
        if self.is_turning:
            # Nếu xe dừng (current_speed = 0) do tránh va chạm, turn_t không tăng -> xe dừng mượt giữa đường cong
            self.turn_t += (self.current_speed * dt) / self.curve_length

            # if: đã đi hết cung (t >= 1) -> chốt trạng thái mới.
            if self.turn_t >= 1.0:
                # Kết thúc cua: chốt hướng mới và offset đích.
                self.is_turning = False;
                self.has_turned = True
                self.direction = self.new_dir;
                self.axis_pos = self.new_axis_pos
                self.offset = self.target_offset
                # Chốt xe đúng điểm cuối cung để hạn chế giật vị trí khi nhập làn.
                self.x, self.y = self.P2

            # else: vẫn đang trên cung -> nội suy vị trí + góc theo tiếp tuyến.
            else:
                # Nội suy vị trí trên đường cong Bezier bậc 2.
                t = self.turn_t;
                u = 1 - t
                self.x = u * u * self.P0[0] + 2 * u * t * self.P1[0] + t * t * self.P2[0]
                self.y = u * u * self.P0[1] + 2 * u * t * self.P1[1] + t * t * self.P2[1]

                # Lấy vector tiếp tuyến để xoay thân xe mượt theo hướng chuyển động.
                dx = 2 * u * (self.P1[0] - self.P0[0]) + 2 * t * (self.P2[0] - self.P1[0])
                dy = 2 * u * (self.P1[1] - self.P0[1]) + 2 * t * (self.P2[1] - self.P1[1])
                target_angle = (math.degrees(math.atan2(-dy, dx)) - 90) % 360

                diff = (target_angle - self.visual_angle + 180) % 360 - 180
                self.visual_angle += diff * 10.0 * dt

        # else lớn 2: xe đi thẳng theo hướng hiện tại (có thể đang đổi làn mềm).
        else:
            # Nếu chưa đúng làn mục tiêu thì dịch ngang từ từ để tránh giật hình.
            if abs(self.offset - self.target_offset) > 0.5:
                shift_speed = 40.0 * dt

                # if/else: tiến offset dần về target_offset theo đúng chiều.
                if self.offset < self.target_offset:
                    self.offset = min(self.offset + shift_speed, self.target_offset)
                else:
                    self.offset = max(self.offset - shift_speed, self.target_offset)

            # Xoay dần về góc chuẩn của hướng hiện tại.
            target_angle = self.angles[self.direction]
            diff = (target_angle - self.visual_angle + 180) % 360 - 180
            self.visual_angle += diff * 8.0 * dt

            # Tiến dọc theo hướng chính với quãng đường = tốc độ * dt.
            dist = self.current_speed * dt

            # if/elif theo hướng để cập nhật trục tiến và trục bám lane.
            if self.direction == SOUTH:
                self.y += dist; self.x = apply_offset(SOUTH, self.offset, self.axis_pos)
            elif self.direction == NORTH:
                self.y -= dist; self.x = apply_offset(NORTH, self.offset, self.axis_pos)
            elif self.direction == EAST:
                self.x += dist; self.y = apply_offset(EAST, self.offset, self.axis_pos)
            elif self.direction == WEST:
                self.x -= dist; self.y = apply_offset(WEST, self.offset, self.axis_pos)

    def draw(self, surface):
        # Vẽ thân xe đã xoay theo góc hiện tại.
        draw_rotated_rect(surface, self.color, self.x, self.y, self.width, self.length, self.visual_angle)

        # if: chỉ hiển thị xi-nhan trước khi xe hoàn tất lần rẽ hiện tại và khi ý định không phải đi thẳng.
        if not self.has_turned and self.turn_intention != "STRAIGHT":
            # Xi nhan nháy theo chu kỳ để thể hiện ý định rẽ.
            # Điều kiện modulo tạo hiệu ứng chớp: 300ms bật, 300ms tắt.
            if pygame.time.get_ticks() % 600 < 300:
                indicator_color = YELLOW_ON
                angle_rad = math.radians(self.visual_angle)

                # if/else: chọn vị trí đèn xi-nhan bên phải hoặc bên trái theo ý định rẽ.
                side = 5 if self.turn_intention == "RIGHT" else -5
                pygame.draw.circle(surface, indicator_color,
                                   (int(self.x + side * math.cos(angle_rad)), int(self.y - side * math.sin(angle_rad))),
                                   2)