"""
Module trung gian cho simulation.

Doc file output JSON tu server va ap dung trang thai den vao cac nut giao.
"""

import json
import os
import time

from config import PHASE_OUTPUT_FILE, PHASE_OUTPUT_REFRESH_SEC
from traffic_light_logic import Intersection
from traffic_light_renderer import draw_traffic_signals


class ControlLightFileReader:
	# Doc file output_control_light.json va cap nhat trang thai den.
	def __init__(self, file_path=None, refresh_sec=None):
		self.file_path = file_path or PHASE_OUTPUT_FILE
		self.refresh_sec = PHASE_OUTPUT_REFRESH_SEC if refresh_sec is None else refresh_sec
		self._last_read_real = 0.0
		self._last_payload = None

	@staticmethod
	def _safe_int(value, default=0):
		try:
			return int(value)
		except (TypeError, ValueError):
			return default

	@staticmethod
	def _safe_float(value, default=0.0):
		try:
			return float(value)
		except (TypeError, ValueError):
			return default

	def _read_payload(self):
		if not os.path.exists(self.file_path):
			return None

		try:
			with open(self.file_path, "r", encoding="utf-8") as f:
				payload = json.load(f)
		except (OSError, json.JSONDecodeError):
			return None

		if not isinstance(payload, dict):
			return None
		return payload

	def _apply_payload(self, intersections, payload):
		data = payload.get("data")
		if not isinstance(data, list):
			return

		by_pos = {(int(ic.cx), int(ic.cy)): ic for ic in intersections}

		for item in data:
			if not isinstance(item, dict):
				continue

			ic = None
			idx = self._safe_int(item.get("index"), default=-1)
			if 0 <= idx < len(intersections):
				ic = intersections[idx]
			else:
				cx = self._safe_int(item.get("cx"), default=None)
				cy = self._safe_int(item.get("cy"), default=None)
				if cx is not None and cy is not None:
					ic = by_pos.get((cx, cy))

			if ic is None:
				continue

			phase_mode = item.get("phase_mode")
			if phase_mode:
				ic.phase_mode = phase_mode

			ic.phase = self._safe_int(item.get("phase_index"), default=ic.phase)
			ic.timer = self._safe_float(item.get("timer"), default=ic.timer)
			ic.green_elapsed = self._safe_float(item.get("green_elapsed"), default=ic.green_elapsed)

			pending = item.get("pending_next")
			ic.pending_next_phase = pending if pending else None

			if hasattr(ic, "last_phase_kind"):
				if hasattr(ic, "_phase_kind"):
					ic.last_phase_kind = ic._phase_kind(ic.phase_mode)
				else:
					ic.last_phase_kind = None

	def update_intersections(self, intersections):
		now = time.time()
		if now - self._last_read_real < self.refresh_sec:
			return

		self._last_read_real = now
		payload = self._read_payload()
		if payload is None:
			if self._last_payload is not None:
				self._apply_payload(intersections, self._last_payload)
			return

		self._last_payload = payload
		self._apply_payload(intersections, payload)


__all__ = ["Intersection", "draw_traffic_signals", "ControlLightFileReader"]