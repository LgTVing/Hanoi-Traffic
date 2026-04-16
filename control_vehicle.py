"""
Bộ điều khiển hành vi phương tiện.

Chịu trách nhiệm cho mỗi frame:
1) Sinh xe mới theo xác suất và mật độ hiện tại.
2) Tính quyền đi (theo đèn), khoảng cách an toàn, trạng thái chờ.
3) Quyết định đổi làn/rẽ và cập nhật vị trí xe.
4) Cập nhật waiting_counts cho từng giao lộ phục vụ điều chỉnh thời gian đèn.
"""

import random

from config import *
from motor import Motorcycle
from car_vehicle import Car
from road_layout import (
    LANES,
    LANE_INTENTIONS,
    apply_offset,
    get_axis_positions_for_direction,
    get_nearest_axis_position,
    get_spawn_position,
    is_inside_cleanup_bounds,
)


class VehicleController:
    # Module này chỉ xử lý hành vi xe: spawn, chạy thẳng, đổi làn, rẽ và dọn xe ra biên.
    def __init__(self, intersections, vehicles):
        # intersections: danh sách các nút giao hiện có trên bản đồ.
        self.intersections = intersections
        # vehicles: danh sách phương tiện dùng chung với lớp SimulationMap.
        self.vehicles = vehicles

    def _lane_span(self):
        # Khoảng cách chuẩn giữa 2 tâm làn liên tiếp.
        if len(LANES) < 2:
            return 24.0
        return min(abs(LANES[i + 1] - LANES[i]) for i in range(len(LANES) - 1))

    def _get_intention_offset_bounds(self, intention):
        # Quy đổi "luồng" sang dải offset liên tục: xe được phép chạy tự do trong toàn dải này.
        centers = LANE_INTENTIONS.get(intention, LANES)
        half_lane = self._lane_span() / 2.0

        lo = min(centers) - half_lane
        hi = max(centers) + half_lane

        # Kẹp lại trong mặt cắt phần đường để không lấn quá mép.
        lo = max(2.0, lo)
        hi = min(R - 2.0, hi)
        return lo, hi

    def _clamp_offset_for_intention(self, intention, offset):
        # Kẹp offset vào dải được phép của luồng hiện tại.
        lo, hi = self._get_intention_offset_bounds(intention)
        return max(lo, min(hi, offset))

    def _sample_lane_offset(self, v, intention, preferred_offset=None):
        # Lấy offset ngẫu nhiên trong dải luồng; không khóa cứng vào tâm làn.
        lo, hi = self._get_intention_offset_bounds(intention)
        if hi <= lo:
            return lo

        is_motor = isinstance(v, Motorcycle)

        if preferred_offset is None:
            base = random.uniform(lo, hi)
        else:
            base = self._clamp_offset_for_intention(intention, preferred_offset)

        # Xe máy dao động ngang lớn hơn để lách vào khe hở nhỏ.
        if is_motor:
            jitter = random.uniform(-6.5, 6.5)
        else:
            jitter = random.uniform(-3.2, 3.2)

        # Đường càng đông thì càng có xu hướng tấp về phía lề phải.
        density = min(1.0, len(self.vehicles) / 160.0)
        curb_bias = density * (2.3 if is_motor else 1.4)

        sampled = base + jitter + curb_bias
        return max(lo, min(hi, sampled))

    def update(self, dt):
        # Bước 1: thử sinh xe mới trước khi tính tương tác.
        self._spawn_vehicles()

        # Bước 2: reset bộ đếm xe chờ của tất cả giao lộ cho frame hiện tại.
        # Vòng for đảm bảo mỗi giao lộ luôn tính queue mới, không giữ dữ liệu frame cũ.
        for ic in self.intersections:
            ic.waiting_counts = {NORTH: 0, SOUTH: 0, EAST: 0, WEST: 0}

        # Reset ý định cho xe vừa hoàn tất cua để quay về trạng thái đi thẳng.
        for v in self.vehicles:
            # if: chỉ reset cho xe vừa hoàn tất một pha cua trong frame trước.
            if v.has_turned:
                v.has_turned = False
                v.turn_intention = "STRAIGHT"
                v.decision_made = False
                v.lane_change_cooldown = max(getattr(v, "lane_change_cooldown", 0.0), 0.6)

                # Sau khi cua xong, đưa xe về lane đi thẳng gần nhất để dòng lưu thông ổn định.
                v.target_offset = self._sample_lane_offset(v, "STRAIGHT", preferred_offset=v.offset)

        # Bước 3: xử lý theo từng hướng để so sánh xe cùng chiều dễ hơn.
        for d in [NORTH, SOUTH, EAST, WEST]:
            # Lọc nhanh tập xe cùng hướng d để giảm chi phí kiểm tra va chạm.
            dir_vehicles = [v for v in self.vehicles if v.direction == d]

            # Duyệt từng xe trong cùng hướng để tính quyết định frame hiện tại.
            for v in dir_vehicles:
                # if: xe cũ chưa có cờ decision_made thì bổ sung mặc định.
                if not hasattr(v, "decision_made"):
                    v.decision_made = False

                # if/else: khởi tạo hoặc giảm dần cooldown đổi làn.
                if not hasattr(v, "lane_change_cooldown"):
                    v.lane_change_cooldown = 0.0
                else:
                    v.lane_change_cooldown = max(0.0, v.lane_change_cooldown - dt)

                # Nếu đang cua, chỉ xử lý chống dồn toa với xe cùng luồng cua.
                if v.is_turning:
                    v.current_speed = v.max_speed

                    # Vòng for: dò các xe khác đang cùng cua để tránh chồng xe trên cung.
                    for other in dir_vehicles:
                        # Bỏ qua chính nó hoặc xe không ở trạng thái cua.
                        if other == v or not other.is_turning:
                            continue

                        # Chỉ so với xe cùng luồng rẽ (cùng intention và cùng lane mục tiêu).
                        if other.turn_intention == v.turn_intention and other.target_offset == v.target_offset:
                            diff_t = other.turn_t - v.turn_t

                            # if: xe khác ở trước trên cung trong khoảng gần.
                            if 0 < diff_t < 0.15:
                                v.current_speed = min(v.current_speed, other.current_speed)

                                # if lồng: quá gần hoặc xe trước đứng hẳn -> xe sau dừng theo.
                                if other.current_speed == 0 or diff_t < 0.06:
                                    v.current_speed = 0

                    # Đã xử lý trạng thái cua thì cập nhật vị trí và sang xe tiếp theo.
                    v.update_position(dt)
                    continue

                # Trạng thái mặc định khi xe đi thẳng (chưa bị ràng buộc bởi xe trước/đèn).
                v.current_speed = v.max_speed
                v.is_waiting = False
                v.is_stopping_for_light = False

                # Tìm giao lộ tiếp theo trên trục hiện tại của xe.
                target_ic = self._get_next_intersection(v)

                # Chọn ý định rẽ ngẫu nhiên khi xe gần tâm giao lộ.
                if target_ic and not v.decision_made:
                    dist_to_center = self._get_dist_to_center(v, target_ic)

                    # if: chỉ ra quyết định trong vùng chuẩn bị vào nút (tránh đổi ý quá sớm/quá muộn).
                    if 0 < dist_to_center < 260:
                        v.turn_intention = random.choices(["STRAIGHT", "LEFT", "RIGHT"], weights=[0.45, 0.30, 0.25])[0]
                        v.target_offset = self._sample_lane_offset(v, v.turn_intention, preferred_offset=v.offset)
                        v.decision_made = True

                # Kích hoạt rẽ khi đến ngưỡng vào nút giao.
                if target_ic and not v.has_turned and v.turn_intention != "STRAIGHT":
                    self._check_and_start_turn(v, target_ic)
                    if v.is_turning:
                        continue

                # Tính khoảng dừng vì đèn đỏ (trừ rẽ phải được đi).
                dist_to_stop_line = 9999
                if target_ic and v.turn_intention != "RIGHT":
                    d_stop = self._get_dist_to_stop(v, target_ic)

                    # if: xe đang trước vạch dừng và luồng không được phép qua.
                    if d_stop > 0 and not target_ic.is_allowed(v.direction, v.turn_intention):
                        dist_to_stop_line = d_stop - (v.length / 2)

                        # if: đủ gần vạch dừng thì đánh dấu trạng thái đang dừng đèn.
                        if dist_to_stop_line < 100:
                            v.is_stopping_for_light = True

                # Tìm xe phía trước trong lane hiện tại theo trục chuyển động.
                closest_ahead = None
                min_dist_ahead = 9999.0
                for other in dir_vehicles:
                    # Bỏ qua chính nó, xe khác trục đường, hoặc xe đang cua (có quỹ đạo riêng).
                    if other == v or other.axis_pos != v.axis_pos or other.is_turning:
                        continue

                    # if: chỉ xét xe đang cùng dải lane hiện tại của v.
                    if not self._lane_overlap(v, other, v.offset, lane_padding=0.8):
                        continue

                    dist_1d = self._forward_distance(v, other)

                    # if: xe nằm phía trước và gần nhất tính đến hiện tại.
                    if dist_1d > 0 and dist_1d < min_dist_ahead:
                        min_dist_ahead = dist_1d
                        closest_ahead = other

                max_allowed_dist = dist_to_stop_line
                if closest_ahead:
                    # Khoảng bám đuôi an toàn có xét chiều dài thân 2 xe và thêm biên đệm.
                    if isinstance(v, Motorcycle) and isinstance(closest_ahead, Motorcycle):
                        follow_extra = 1.5
                    elif isinstance(v, Motorcycle) or isinstance(closest_ahead, Motorcycle):
                        follow_extra = 2.5
                    else:
                        follow_extra = 3.5

                    safe_follow_dist = min_dist_ahead - (v.length / 2 + closest_ahead.length / 2 + follow_extra)
                    max_allowed_dist = min(max_allowed_dist, safe_follow_dist)

                    # Nếu bị chặn phía trước thì thử lách trái/phải bằng kiểm tra vùng chiếm dụng đầy (AABB).
                    if (v.is_stopping_for_light and safe_follow_dist < 14) or (
                        not v.is_stopping_for_light and v.max_speed > closest_ahead.current_speed and safe_follow_dist < 30
                    ):
                        if v.lane_change_cooldown <= 0.0 and abs(v.offset - v.target_offset) <= 0.5:
                            target_offset = self._pick_best_lane_change_offset(v, dir_vehicles, blocker=closest_ahead)
                            if target_offset is not None:
                                v.target_offset = target_offset
                                v.lane_change_cooldown = 0.9

                # Áp tốc độ theo khoảng trống cho phép.
                if max_allowed_dist <= 0:
                    # if: không còn khoảng trống -> dừng hẳn.
                    v.current_speed = 0
                    v.is_waiting = True
                elif max_allowed_dist < v.current_speed * dt:
                    # elif: còn trống nhưng không đủ cho tốc độ hiện tại -> giảm tốc vừa đủ.
                    v.current_speed = max_allowed_dist / dt
                    v.is_waiting = True

                # if: ghi nhận xe chờ để bộ đèn dùng cho pha kế tiếp.
                if v.is_waiting and target_ic and v.turn_intention != "RIGHT":
                    target_ic.waiting_counts[v.direction] += 1

                v.update_position(dt)

        # Dọn xe theo biên hạ tầng hiện tại (không phụ thuộc cứng vào WINDOW_SIZE).
        self.vehicles[:] = [v for v in self.vehicles if is_inside_cleanup_bounds(v.x, v.y)]

    def _spawn_vehicles(self):
        # Giới hạn tổng số xe để giữ hiệu năng ổn định.
        if len(self.vehicles) < 200:
            # Vòng for 1: duyệt từng hướng giao thông.
            for d in [NORTH, SOUTH, EAST, WEST]:
                # Vòng for 2: duyệt từng trục đường của hướng đó.
                for pos in get_axis_positions_for_direction(d):
                    # if: xác suất spawn theo frame, điều chỉnh mật độ xe vào hệ thống.
                    if random.random() < 0.035:
                        # Sinh phần lớn là xe máy, phần còn lại là ô tô.
                        new_v = Motorcycle(d, pos) if random.random() <= 0.85 else Car(d, pos)

                        # Gán trước ý định và lane mục tiêu để tránh đổi lane quá đột ngột ngay sau spawn.
                        new_v.turn_intention = random.choices(["STRAIGHT", "LEFT", "RIGHT"], weights=[0.45, 0.30, 0.25])[0]
                        new_v.target_offset = self._sample_lane_offset(new_v, new_v.turn_intention)
                        new_v.offset = new_v.target_offset
                        new_v.decision_made = True

                        # Mỗi xe có cooldown lệch nhẹ để phân tán hành vi đổi làn theo thời gian.
                        new_v.lane_change_cooldown = random.uniform(0.1, 0.6)

                        # Spawn từ đầu đường lấy trực tiếp từ dữ liệu hạ tầng.
                        new_v.x, new_v.y = get_spawn_position(d, pos, new_v.offset)

                        safe_to_spawn = True

                        # Vòng for 3: kiểm tra khoảng cách với xe đã tồn tại cùng trục để tránh spawn chồng xe.
                        for existing_v in self.vehicles:
                            if existing_v.direction == d and existing_v.axis_pos == pos and not existing_v.is_turning:
                                dist_1d = abs(existing_v.get_pos_1d() - new_v.get_pos_1d())

                                if isinstance(new_v, Motorcycle) and isinstance(existing_v, Motorcycle):
                                    min_spawn_gap = 28
                                elif isinstance(new_v, Motorcycle) or isinstance(existing_v, Motorcycle):
                                    min_spawn_gap = 34
                                else:
                                    min_spawn_gap = 44

                                # if: quá gần xe hiện có -> hủy spawn ở frame này.
                                if dist_1d < min_spawn_gap:
                                    safe_to_spawn = False
                                    break

                        # if: chỉ thêm xe khi đã qua kiểm tra an toàn spawn.
                        if safe_to_spawn:
                            self.vehicles.append(new_v)

    def _get_dist_to_center(self, v, ic):
        # Khoảng cách có dấu từ xe tới tâm giao lộ theo chiều chuyển động hiện tại.
        # Dấu dương nghĩa là giao lộ ở phía trước xe.
        if v.direction == SOUTH:
            return ic.cy - v.y
        if v.direction == NORTH:
            return v.y - ic.cy
        if v.direction == EAST:
            return ic.cx - v.x
        if v.direction == WEST:
            return v.x - ic.cx

    def _get_dist_to_stop(self, v, ic):
        # Khoảng cách có dấu từ đầu xe tới vạch dừng theo từng hướng.
        if v.direction == SOUTH:
            return (ic.cy - STOP_LINE_DIST) - v.y
        if v.direction == NORTH:
            return v.y - (ic.cy + STOP_LINE_DIST)
        if v.direction == EAST:
            return (ic.cx - STOP_LINE_DIST) - v.x
        if v.direction == WEST:
            return v.x - (ic.cx + STOP_LINE_DIST)

    def _get_next_intersection(self, v):
        # Tìm giao lộ gần nhất ở phía trước cùng trục đường với xe.
        closest_ic = None
        min_d = 9999

        # Vòng for: duyệt toàn bộ nút giao rồi lọc theo trục + phía trước.
        for ic in self.intersections:
            # if: xe chạy dọc thì chỉ xét giao lộ có cùng trục X (cx).
            if v.direction in [NORTH, SOUTH] and ic.cx != v.axis_pos:
                continue

            # if: xe chạy ngang thì chỉ xét giao lộ có cùng trục Y (cy).
            if v.direction in [EAST, WEST] and ic.cy != v.axis_pos:
                continue

            d = self._get_dist_to_center(v, ic)

            # if: chọn giao lộ ở phía trước gần nhất; cho phép âm nhẹ để tránh giật ở vùng giao.
            if -100 < d < min_d:
                min_d = d
                closest_ic = ic
        return closest_ic

    def _lane_overlap(self, v, other, target_offset, lane_padding=1.0):
        # Hai xe được xem "cùng lane vùng xét" nếu chênh offset nhỏ hơn tổng nửa bề rộng + đệm.
        overlap_margin = (v.width / 2 + other.width / 2 + lane_padding)
        return abs(target_offset - other.offset) < overlap_margin

    def _aabb_for_vehicle(self, v, offset=None, front_extra=0.0, back_extra=0.0, side_extra=0.0):
        # Dùng AABB đầy để xét va chạm vùng thân xe (không chỉ xét biên).
        # offset cho phép đánh giá xe tại lane giả định (khi thử đổi làn).
        off = v.offset if offset is None else offset

        # if: xe chạy dọc => chiều dài xe map theo trục Y.
        if v.direction in [NORTH, SOUTH]:
            cx = apply_offset(v.direction, off, v.axis_pos)
            cy = v.y
            half_w = v.width / 2 + side_extra
            half_l = v.length / 2
            x_min = cx - half_w
            x_max = cx + half_w

            # if/else: front/back extra cộng về phía trước hoặc phía sau tùy chiều chạy.
            if v.direction == SOUTH:
                y_min = cy - half_l - back_extra
                y_max = cy + half_l + front_extra
            else:
                y_min = cy - half_l - front_extra
                y_max = cy + half_l + back_extra

        # else: xe chạy ngang => chiều dài xe map theo trục X.
        else:
            cx = v.x
            cy = apply_offset(v.direction, off, v.axis_pos)
            half_w = v.width / 2 + side_extra
            half_l = v.length / 2
            y_min = cy - half_w
            y_max = cy + half_w

            # if/else: front/back extra theo chiều chạy ngang.
            if v.direction == EAST:
                x_min = cx - half_l - back_extra
                x_max = cx + half_l + front_extra
            else:
                x_min = cx - half_l - front_extra
                x_max = cx + half_l + back_extra

        return (x_min, y_min, x_max, y_max)

    def _aabb_overlap(self, box_a, box_b):
        # Công thức tách trục: không chồng nếu một hộp nằm hoàn toàn ngoài hộp kia theo X hoặc Y.
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return not (ax2 < bx1 or bx2 < ax1 or ay2 < by1 or by2 < ay1)

    def _point_in_aabb(self, px, py, box):
        # Kiểm tra điểm thăm dò có nằm trong vùng chiếm dụng của hộp không.
        x1, y1, x2, y2 = box
        return x1 <= px <= x2 and y1 <= py <= y2

    def _union_aabb(self, box_a, box_b):
        # Hợp 2 hộp để lấy vùng bao phủ tổng khi xe chuyển từ lane hiện tại sang lane đích.
        ax1, ay1, ax2, ay2 = box_a
        bx1, by1, bx2, by2 = box_b
        return (min(ax1, bx1), min(ay1, by1), max(ax2, bx2), max(ay2, by2))

    def _forward_distance(self, v, other):
        # Chuẩn hóa khoảng cách trước/sau về một dấu chung: dương = other ở phía trước.
        dist_1d = other.get_pos_1d() - v.get_pos_1d()
        if v.direction in [NORTH, WEST]:
            dist_1d = -dist_1d
        return dist_1d

    def _forward_clearance_in_lane(self, v, dir_vehicles, target_offset):
        # Khoảng trống phía trước tại lane đích, trừ nửa chiều dài 2 xe.
        min_clear = 9999.0

        # Vòng for: chỉ xét xe cùng trục, không xét xe đang cua.
        for other in dir_vehicles:
            if other == v or other.axis_pos != v.axis_pos or other.is_turning:
                continue
            if not self._lane_overlap(v, other, target_offset, lane_padding=0.8):
                continue

            dist = self._forward_distance(v, other)

            # if: chỉ quan tâm xe nằm phía trước.
            if dist > 0:
                clearance = dist - (v.length / 2 + other.length / 2 + 2)
                min_clear = min(min_clear, clearance)
        return min_clear

    def _forward_probe_free(self, v, dir_vehicles, target_offset, probe_distance):
        # Dịch sang lane mục tiêu và kiểm tra điểm trước mũi xe như luồng giao thông thực tế.
        # if/elif: xác định điểm probe nằm ở phía trước đầu xe theo hướng chạy.
        if v.direction == SOUTH:
            px = apply_offset(SOUTH, target_offset, v.axis_pos)
            py = v.y + v.length / 2 + probe_distance
        elif v.direction == NORTH:
            px = apply_offset(NORTH, target_offset, v.axis_pos)
            py = v.y - v.length / 2 - probe_distance
        elif v.direction == EAST:
            px = v.x + v.length / 2 + probe_distance
            py = apply_offset(EAST, target_offset, v.axis_pos)
        else:  # WEST
            px = v.x - v.length / 2 - probe_distance
            py = apply_offset(WEST, target_offset, v.axis_pos)

        # Vòng for: nếu probe rơi vào AABB của bất kỳ xe nào thì coi lane đích chưa an toàn.
        for other in dir_vehicles:
            if other == v or other.axis_pos != v.axis_pos or other.is_turning:
                continue
            other_box = self._aabb_for_vehicle(other, side_extra=0.6)
            if self._point_in_aabb(px, py, other_box):
                return False
        return True

    def _is_lane_change_path_clear(self, v, dir_vehicles, target_offset):
        # Vùng chuyển làn gồm hợp của thân xe hiện tại + thân xe ở lane đích.
        transition_front = max(v.length * 0.45, 6)
        transition_back = max(v.length * 0.60, 8)
        current_box = self._aabb_for_vehicle(v, offset=v.offset, front_extra=transition_front, back_extra=transition_back, side_extra=1.0)
        target_box = self._aabb_for_vehicle(v, offset=target_offset, front_extra=transition_front, back_extra=transition_back, side_extra=1.0)
        transition_zone = self._union_aabb(current_box, target_box)

        # Vòng for: chỉ cần chồng với 1 xe là loại ngay lane đích.
        for other in dir_vehicles:
            if other == v or other.axis_pos != v.axis_pos or other.is_turning:
                continue
            other_box = self._aabb_for_vehicle(other, side_extra=0.6)
            if self._aabb_overlap(transition_zone, other_box):
                return False
        return True

    def _evaluate_lane_candidate(self, v, dir_vehicles, target_offset):
        # Bên trống + phía trước còn chỗ + vùng chuyển làn không va chạm.
        # if 1: vùng chuyển làn giao xe khác -> loại.
        if not self._is_lane_change_path_clear(v, dir_vehicles, target_offset):
            return None

        safety_gap = max(6.0, v.length * 0.22)
        front_clearance = self._forward_clearance_in_lane(v, dir_vehicles, target_offset)
        required_clearance = v.length * 0.75 + safety_gap

        # if 2: khoảng trống phía trước lane đích chưa đủ -> loại.
        if front_clearance < required_clearance:
            return None

        probe_distance = required_clearance

        # if 3: điểm probe trước mũi xe bị chặn -> loại.
        if not self._forward_probe_free(v, dir_vehicles, target_offset, probe_distance):
            return None

        # Trả về điểm số cơ sở (khoảng trống trước càng lớn càng tốt).
        return front_clearance

    def _pick_best_lane_change_offset(self, v, dir_vehicles, blocker=None):
        low, high = self._get_intention_offset_bounds(v.turn_intention)
        current_offset = self._clamp_offset_for_intention(v.turn_intention, v.offset)

        # Dải quá hẹp thì không đủ chỗ để đổi làn ngang.
        if high - low < 1.5:
            return None

        candidates = []

        def _add_candidate(raw_offset):
            off = max(low, min(high, raw_offset))

            # Bỏ ứng viên quá gần vị trí hiện tại để tránh đổi làn giả.
            if abs(off - current_offset) < 1.0:
                return

            # Tránh trùng ứng viên gây tốn kiểm tra.
            for existing in candidates:
                if abs(existing - off) < 0.7:
                    return
            candidates.append(off)

        # Quét các bước lệch ngang để thử chui vào khe trống gần.
        for delta in (-18, -12, -8, -5, 5, 8, 12, 18):
            _add_candidate(current_offset + delta)

        # Bổ sung 3 mốc đại diện của dải luồng.
        _add_candidate(low + 0.8)
        _add_candidate((low + high) / 2.0)
        _add_candidate(high - 0.8)

        # Nếu có xe chặn, thử thêm vị trí né sang 2 bên thân xe đó.
        if blocker is not None:
            side_gap = v.width / 2 + blocker.width / 2 + 1.2
            _add_candidate(blocker.offset - side_gap - 1.5)
            _add_candidate(blocker.offset + side_gap + 1.5)

        # Thêm vài điểm ngẫu nhiên để xe có thể chèn vào các khe lạ.
        for _ in range(3):
            _add_candidate(random.uniform(low, high))

        if not candidates:
            return None

        best_offset = None
        best_score = -1.0

        # Vòng for: chấm điểm toàn bộ lane ứng viên, chọn lane điểm cao nhất.
        for t_off in candidates:
            score = self._evaluate_lane_candidate(v, dir_vehicles, t_off)
            if score is None:
                continue

            # Hạn chế đổi quá xa khi lợi ích tương đương để hành vi mượt hơn.
            lane_jump = abs(t_off - current_offset)
            score -= lane_jump * 0.08

            # Khi có vật cản trước mặt, ưu tiên offset tách xa xe chặn.
            if blocker is not None:
                score += abs(t_off - blocker.offset) * 0.35

            # Ưu tiên nhẹ phía gần lề phải khi mật độ cao.
            score += (t_off - low) * 0.03

            # if: cập nhật phương án tốt nhất hiện tại.
            if score > best_score:
                best_score = score
                best_offset = t_off

        return best_offset

    def _check_and_start_turn(self, v, ic):
        # if: rẽ trái chỉ được kích hoạt khi đèn cho phép.
        if v.turn_intention == "LEFT" and not ic.is_allowed(v.direction, "LEFT"):
            return

        # trigger điều chỉnh ngưỡng bắt đầu cua (rẽ phải thường bắt đầu sớm hơn).
        trigger = BRANCH_D if v.turn_intention == "RIGHT" else -15

        # if/elif: kiểm tra xe đã vượt qua ngưỡng kích hoạt cua theo từng hướng chưa.
        if v.direction == SOUTH:
            passed = v.y >= ic.cy - trigger
        elif v.direction == NORTH:
            passed = v.y <= ic.cy + trigger
        elif v.direction == EAST:
            passed = v.x >= ic.cx - trigger
        elif v.direction == WEST:
            passed = v.x <= ic.cx + trigger
        else:
            passed = False

        # if: chưa đến điểm vào cua thì chưa làm gì.
        if not passed:
            return

        # Bám lane mục tiêu cho luồng rẽ; nếu lệch nhiều thì fallback về lane gần nhất.
        new_off = self._clamp_offset_for_intention(v.turn_intention, v.target_offset)

        # P0 luôn là vị trí hiện tại của xe tại thời điểm bắt đầu cua.
        P0 = (v.x, v.y)

        if v.turn_intention == "RIGHT":
            out_dist = BRANCH_D
            push = BRANCH_D

            # Mỗi nhánh hướng tạo bộ điểm P1/P2 khác nhau để xe bo cua đúng hình học nút giao.
            if v.direction == SOUTH:
                new_dir = WEST
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cy)
                end_y = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (ic.cx - out_dist, end_y)
                P1 = (ic.cx - push, ic.cy - push)
            elif v.direction == NORTH:
                new_dir = EAST
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cy)
                end_y = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (ic.cx + out_dist, end_y)
                P1 = (ic.cx + push, ic.cy + push)
            elif v.direction == EAST:
                new_dir = SOUTH
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cx)
                end_x = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (end_x, ic.cy + out_dist)
                P1 = (ic.cx - push, ic.cy + push)
            elif v.direction == WEST:
                new_dir = NORTH
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cx)
                end_x = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (end_x, ic.cy - out_dist)
                P1 = (ic.cx + push, ic.cy - push)
        else:
            # Luồng rẽ trái quay 90 độ rồi nhập vào lane sẵn có của đường mới.
            out_dist = 60

            # if/elif theo hướng để chọn đường đích và bộ điểm điều khiển phù hợp.
            if v.direction == SOUTH:
                new_dir = EAST
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cy)
                end_y = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (ic.cx + out_dist, end_y)
                P1 = (P0[0], P2[1])
            elif v.direction == NORTH:
                new_dir = WEST
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cy)
                end_y = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (ic.cx - out_dist, end_y)
                P1 = (P0[0], P2[1])
            elif v.direction == EAST:
                new_dir = NORTH
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cx)
                end_x = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (end_x, ic.cy - out_dist)
                P1 = (P2[0], P0[1])
            elif v.direction == WEST:
                new_dir = SOUTH
                new_axis_pos = get_nearest_axis_position(new_dir, ic.cx)
                end_x = apply_offset(new_dir, new_off, new_axis_pos)
                P2 = (end_x, ic.cy + out_dist)
                P1 = (P2[0], P0[1])

        v.start_turn(P0, P1, P2, new_dir, new_off, new_axis_pos)
