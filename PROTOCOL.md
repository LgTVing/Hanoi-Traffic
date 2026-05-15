# Giao Thức Kết Nối — Hệ Thống Đèn Giao Thông Thích Ứng

> **Mục đích:** Mô tả giao thức truyền thông giữa 3 thành phần: **Pi5** (nhận diện xe) → **Server** (thuật toán điều phối) → **Simulator** (giả lập giao thông). AI implement theo tài liệu này cần đọc toàn bộ trước khi viết code.

---

## 1. Kiến Trúc Tổng Quan

```
[Camera] → [Pi5: xử lý ảnh, đếm xe]
                    │  MQTT JSON (định kỳ)
                    ▼
                    │  MQTT JSON (khi có thay đổi)
                    ▼
        [Simulator: cập nhật đèn theo lệnh]
```

**Tất cả giao tiếp dùng JSON qua MQTT.**

---

## 2. Sơ Đồ Ngã Tư & Lane ID

Giả lập có 4 ngã tư bố cục 2×2. Lane được đánh số theo chiều kim đồng hồ bắt đầu từ 12h (hướng Bắc).

```
┌─────────────────┬─────────────────┐
│  Ngã tư 0 (TL)  │  Ngã tư 1 (TR)  │
│  N=10  E=3      │  N=14  E=2      │
│  S=9   W=0      │  S=13  W=1      │
├─────────────────┼─────────────────┤
│  Ngã tư 2 (BL)  │  Ngã tư 3 (BR)  │
│  N=11  E=7      │  N=15  E=6      │
│  S=8   W=4      │  S=12  W=5      │
└─────────────────┴─────────────────┘
```

### Bảng mapping đầy đủ

| Intersection ID | Vị trí | Lane Bắc (N) | Lane Đông (E) | Lane Nam (S) | Lane Tây (W) |
|:-:|:-:|:-:|:-:|:-:|:-:|
| 0 | Top-Left     | 10 | 3  | 9  | 0  |
| 1 | Top-Right    | 14 | 2  | 13 | 1  |
| 2 | Bottom-Left  | 11 | 7  | 8  | 4  |
| 3 | Bottom-Right | 15 | 6  | 12 | 5  |

**Quy ước hướng:** N = xe đang ở hướng Bắc chờ vào ngã tư, tương tự với E/S/W.

### Đèn tín hiệu mỗi làn

Mỗi làn có **2 đèn độc lập**:
- `straight` — đèn đi thẳng
- `left` — đèn rẽ trái

---

## 3. Pi5 → Server: Báo Cáo Số Lượng Xe

### Endpoint

```
TOPIC: traffic/telemetry
```

Pi5 gửi định kỳ (khuyến nghị mỗi 0.5 giây). Mỗi gói chứa số xe đếm được tại thời điểm đó cho tất cả lanes.

### Payload

```json
{
  "timestamp": 1778784448,
  "device_id": "pi5_intersection_master",
  "data": [
    { "lane": 0, "cars": 0, "bikes": 2 },
    { "lane": 1, "cars": 4, "bikes": 34 },
    { "lane": 2, "cars": 0, "bikes": 4 },
    { "lane": 3, "cars": 2, "bikes": 5 },
    { "lane": 4, "cars": 0, "bikes": 2 },
    { "lane": 5, "cars": 0, "bikes": 33 },
    { "lane": 6, "cars": 1, "bikes": 2 },
    { "lane": 7, "cars": 10, "bikes": 33 },
    { "lane": 8, "cars": 1, "bikes": 1 },
    { "lane": 9, "cars": 0, "bikes": 3 },
    { "lane": 10, "cars": 0, "bikes": 2 },
    { "lane": 11, "cars": 0, "bikes": 9 },
    { "lane": 12, "cars": 0, "bikes": 3 },
    { "lane": 13, "cars": 3, "bikes": 11 },
    { "lane": 14, "cars": 0, "bikes": 2 },
    { "lane": 15, "cars": 0, "bikes": 3 }
  ]
}
```

---

## 4. Server → Simulator: Điều Khiển Đèn

### Endpoint (Simulator lắng nghe)

```
TOPIC: traffic/lights
```

Server chỉ gửi khi thuật toán **quyết định thay đổi**. Không gửi định kỳ nếu không có thay đổi.

### Payload

```json
{
  "timestamp": 1778784448,
  "command_id": "cmd-00342",
  "intersections": [
    {
      "intersection_id": 0,
      "lanes": [
        {
          "lane_id": 10,
          "straight": { "state": "green", "duration": 45 },
          "left":     { "state": "red",   "duration": 45 }
        },
        {
          "lane_id": 3,
          "straight": { "state": "green", "duration": 45 },
          "left":     { "state": "green", "duration": 20 }
        }
      ]
    },
    {
      "intersection_id": 2,
      "lanes": [
        {
          "lane_id": 7,
          "straight": { "state": "red", "duration": 30 },
          "left":     { "state": "red", "duration": 30 }
        }
      ]
    }
  ]
}
```

### Các trường chính

| Trường | Kiểu | Mô tả |
|--------|------|-------|
| `intersections` | array | Chỉ liệt kê ngã tư **có thay đổi** |
| `lanes` | array | Chỉ liệt kê làn **có thay đổi** trong ngã tư đó |
| `straight` / `left` | object | Trạng thái đèn đi thẳng / rẽ trái |
| `state` | string | `"green"`, `"red"`, hoặc `"yellow"` |
| `duration` | integer (giây) | Thời gian của trạng thái này |

Lệnh có hiệu lực **ngay khi Simulator nhận được**.

---

## 5. Cấu Hình Kết Nối

**Broker MQTT:**
```
IP=3.107.18.217
PORT=1883
```

## 6. Pipeline
Tôi dùng camera pi5 để quay màn hình giả lập. pi5 gửi số lượng xe mỗi làn lên server. Server có thuật toán chạy và gửi json điều khiển đèn. Sau đó giả lập lắng nghe tín hiệu điều khiển để điều chỉnh đèn đỏ

<!-- ## 6. Thứ Tự Khởi Động

1. **Simulator** — khởi động trước, lắng nghe port
2. **Server** — khởi động sau
3. **Pi5** — bật camera, bắt đầu gửi dữ liệu -->
