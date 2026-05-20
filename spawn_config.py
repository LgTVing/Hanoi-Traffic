# spawn_config.py
from config import NORTH, SOUTH, EAST, WEST

# Cấu hình tỉ lệ sinh xe ở các hướng.
# Ví dụ: với config này, số xe sinh ra từ hướng Đông (EAST) và hướng Bắc (NORTH) 
# sẽ đông gấp nhiều lần xe từ hướng Tây (WEST), Nam (SOUTH).
SPAWN_RATES = {
	NORTH: 10,
	SOUTH: 0.2,
	EAST: 0.2,
	WEST: 10,
}