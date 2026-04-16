"""
Module tương thích ngược cho code cũ.

Code mới nên import trực tiếp:
- Intersection từ traffic_light_logic
- draw_traffic_signals từ traffic_light_renderer
"""

from traffic_light_logic import Intersection
from traffic_light_renderer import draw_traffic_signals

__all__ = ["Intersection", "draw_traffic_signals"]