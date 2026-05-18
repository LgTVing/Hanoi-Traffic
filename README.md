# Adaptive Traffic Light Controller (MQTT)

Tai lieu nay mo ta thuat toan toi uu den giao thong va cach ket noi MQTT trong file thuattoan.py.

## 1) Dau vao tu camera/AI (MQTT telemetry)

Du lieu gui len TOPIC `traffic/telemetry` theo dang JSON:

```json
{
    "timestamp": 1778784448,
    "device_id": "pi5_intersection_master",
    "data": [
        {"lane": 0, "cars": 0, "bikes": 2},
        {"lane": 1, "cars": 4, "bikes": 34}
    ]
}
```

- Moi phan tu `data` la mot lane.
- Thuat toan quy doi ve PCU: `PCU = cars * PCU_CAR + bikes * PCU_BIKE`.

## 2) Mapping lane -> huong vao nut giao

Mapping tu PROTOCOL.md duoc giu nguyen trong thuattoan.py:

```text
0: N=10 E=3  S=9  W=0
1: N=14 E=2  S=13 W=1
2: N=11 E=7  S=8  W=4
3: N=15 E=6  S=12 W=5
```

Tu mapping nay, moi nut giao co 4 huong vao (N/E/S/W). Thuat toan tinh hang cho theo huong de quyet dinh pha.

## 3) Logic toi uu pha den (giu nguyen thong so)

Thuat toan trong thuattoan.py duoc sao chep tu traffic_light_logic.py, gom cac y chinh:

- **Luan phien STRAIGHT <-> LEFT** de dam bao cong bang.
- **Tinh ap luc (pressure)** = (so xe cho) * (thoi gian cho) de uu tien pha.
- **Gioi han do toi da (MAX_RED_TIME_SEC)** cho tung truc NS/EW.
- **Khong cho 1 truc xanh qua 2 pha lien tiep** (MAX_CONSECUTIVE_AXIS_GREENS = 2).
- **Rut ngan pha hien tai** neu chenh lech nhu cau giua 2 truc qua lon.
- **Min/Max green** cho moi pha, LEFT co gioi han rieng.

Thong so hien tai (giu nguyen):

- MIN_GREEN_TIME = 15.0
- MAX_GREEN_TIME = 35.0
- LEFT_MIN_GREEN_TIME = 9.0
- LEFT_MAX_GREEN_TIME = 28.0
- ALL_RED_TIME = 0.8
- PASSAGE_TIME = 2.0
- PRESSURE_SWITCH_DELTA = 2.0
- PRESSURE_SWITCH_HOLD_SEC = 2.0
- MAX_RED_TIME_SEC = 65.0
- RED_DEMAND_MIN = 0.5
- MAX_CONSECUTIVE_AXIS_GREENS = 2
- AXIS_DEMAND_SWITCH_DELTA = 6.0
- AXIS_DEMAND_SWITCH_HOLD_SEC = 1.0
- TURN_INTENTION_WEIGHTS = [0.45, 0.30, 0.25]

## 4) Dau ra dieu khien den (MQTT control)

Lenh gui len TOPIC `traffic/lights` theo dung format:

```json
{
    "timestamp": 1778784500,
    "command_id": "cmd-1234abcd",
    "intersections": [
        {
            "intersection_id": 0,
            "lanes": [
                {"lane_id": 10, "straight": {"state": "green", "duration": 12}, "left": {"state": "red", "duration": 12}},
                {"lane_id": 9,  "straight": {"state": "green", "duration": 12}, "left": {"state": "red", "duration": 12}},
                {"lane_id": 3,  "straight": {"state": "red",   "duration": 12}, "left": {"state": "red", "duration": 12}},
                {"lane_id": 0,  "straight": {"state": "red",   "duration": 12}, "left": {"state": "red", "duration": 12}}
            ]
        }
    ]
}
```

`duration` la so giay con lai cua pha hien tai, duoc lam tron len.

## 5) Cach chay

- Chay broker MQTT.
- Run script:

```bash
python thuattoan.py
```

- Khi co telemetry, script se cap nhat hang cho va tu dong dieu khien pha.

## 6) Luu y

- Neu telemetry mat hon TELEMETRY_STALE_SEC (5s), thuat toan se ve 0 (giam ap luc).
- Du lieu re trai/di thang dang la uoc tinh theo TURN_INTENTION_WEIGHTS.