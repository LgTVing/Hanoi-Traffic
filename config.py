# config.py

# File cấu hình trung tâm cho toàn bộ mô phỏng.
# Mọi module (đường, xe, đèn, hiển thị) đều đọc hằng số ở đây để thống nhất hành vi.

# Kích thước canvas mô phỏng (đơn vị: pixel).
# Giá trị này chủ yếu dùng làm mặc định ban đầu trước khi layout được đồng bộ theo màn hình thật.
WINDOW_SIZE = 1000
# Chế độ hiển thị: fullscreen theo độ phân giải thật của màn hình.
FULLSCREEN_ENABLED = True
# Kích thước fallback khi không chạy fullscreen.
# Hai giá trị này chỉ có tác dụng khi FULLSCREEN_ENABLED = False.
DEFAULT_SCREEN_WIDTH = 1920
DEFAULT_SCREEN_HEIGHT = 1080

# Cấu hình lưới ngã tư tự động theo màn hình.
# Ví dụ 2x2 => tổng cộng 4 giao lộ từ tích Descartes của trục X và trục Y.
INTERSECTION_COLS = 2
INTERSECTION_ROWS = 2
# Lề cố định từ tâm ngã tư gần biên tới mép màn hình.
# Giá trị càng lớn thì giao lộ càng nằm sâu vào giữa màn hình.
INTERSECTION_EDGE_MARGIN = 260

# Nếu đặt list cụ thể thì hệ thống sẽ ưu tiên dùng trực tiếp các vị trí này.
# Đặt None để dùng cơ chế tự động theo INTERSECTION_* và kích thước màn hình.
# Khi muốn "khoá" giao lộ theo toạ độ tùy chỉnh, chỉ cần thay None bằng list số nguyên.
CUSTOM_ROAD_X_POSITIONS = None
CUSTOM_ROAD_Y_POSITIONS = None

# ROAD_WIDTH = 160
# R = ROAD_WIDTH // 2
# Tọa độ trục dọc/ngang của mạng đường; kết hợp tạo thành các giao lộ.
# ROAD_POSITIONS đang được giữ lại như dữ liệu tham khảo lịch sử; logic hiện tại dùng ROAD_X/Y riêng.
ROAD_POSITIONS = [300, 700]

# Hình học nút giao và vạch dừng.
# ROAD_WIDTH: tổng bề rộng phần đường cho cả 2 chiều xe chạy trên một trục.
ROAD_WIDTH = 200
# R: nửa bề rộng đường, hay dùng khi tính biên trái/phải hoặc trên/dưới quanh trục.
R = ROAD_WIDTH // 2
# BRANCH_D: khoảng đẩy hình học cho nhánh rẽ (đặc biệt rẽ phải và vùng bo góc).
BRANCH_D = 160
# STOP_LINE_DIST: khoảng cách từ tâm nút giao tới vạch dừng đèn.
STOP_LINE_DIST = 105
# BRANCH_DIST: hằng số dự phòng cho các phép tính rẽ/nhánh (giữ để mở rộng).
BRANCH_DIST = 160
# SLIP_START, SLIP_OUT: tham số bo cong cho nhánh slip lane khi vẽ đảo.
SLIP_START = 60
SLIP_OUT = 95

# Tham số chu kỳ đèn tín hiệu.
# BASE_GREEN_TIME: xanh cơ sở khi hàng chờ thấp.
BASE_GREEN_TIME = 15.0
# MAX_GREEN_TIME: trần xanh tối đa để tránh một hướng giữ đèn quá lâu.
MAX_GREEN_TIME = 35.0
# YELLOW_TIME hiện chưa dùng trong controller hiện tại (chu kỳ đang dùng ALL_RED xen kẽ).
YELLOW_TIME = 3.0

# Bảng màu dùng cho đèn tín hiệu.
GREEN_ON = (0, 255, 0)
GREEN_OFF = (0, 60, 0)
YELLOW_ON = (255, 255, 0)
YELLOW_OFF = (60, 60, 0)
RED_ON = (255, 0, 0)
RED_OFF = (60, 0, 0)

# Bảng màu dùng cho mặt đường và nền.
ROAD_COLOR = (50, 50, 50)
LINE_COLOR = (255, 255, 0)
WHITE = (255, 255, 255)
BG_COLOR = WHITE
ISLAND_COLOR = (46, 160, 67)
KERB_COLOR = (200, 200, 200)

# Nhãn hướng chuyển động thống nhất toàn hệ thống.
# Dùng chuỗi thay vì số để log/debug dễ đọc.
NORTH, SOUTH, EAST, WEST = "NORTH", "SOUTH", "EAST", "WEST"

# Intelligent Driver Model (IDM) parameters (longitudinal control)
# Units: distances in pixels, time in seconds, speed in pixels/sec
IDM_A = 1.2       # maximum acceleration (pixels/s^2)
IDM_B = 2.0       # comfortable deceleration (pixels/s^2)
IDM_T = 1.2       # desired time headway (s)
IDM_S0 = 4.0      # minimum distance (pixels)
IDM_DELTA = 4.0   # acceleration exponent