import paho.mqtt.client as mqtt
import json
import time

BROKER = "3.107.18.217"
PORT = 1883
TOPIC = "traffic/lights"

def send_command(client, command_id, intersections_data):
    payload = {
        "timestamp": int(time.time()),
        "command_id": command_id,
        "intersections": intersections_data
    }
    client.publish(TOPIC, json.dumps(payload))
    print(f"[{time.strftime('%H:%M:%S')}] Sent {command_id}")

# 4 intersections, 4 directions per intersection -> lane ID mapping
# Theo giao thức PROTOCOL.md
lane_mapping = {
    0: {"NORTH": 10, "EAST": 3, "SOUTH": 9, "WEST": 0},
    1: {"NORTH": 14, "EAST": 2, "SOUTH": 13, "WEST": 1},
    2: {"NORTH": 11, "EAST": 7, "SOUTH": 8, "WEST": 4},
    3: {"NORTH": 15, "EAST": 6, "SOUTH": 12, "WEST": 5}
}

def get_intersections_payload(mode, duration):
    intersections = []
    for i_id, lanes in lane_mapping.items():
        lane_configs = []
        for dir_name, lane_id in lanes.items():
            state_straight = "red"
            state_left = "red"
            
            if mode == "NS_STRAIGHT" and dir_name in ["NORTH", "SOUTH"]:
                state_straight = "green"
            elif mode == "NS_LEFT" and dir_name in ["NORTH", "SOUTH"]:
                state_left = "green"
            elif mode == "EW_STRAIGHT" and dir_name in ["EAST", "WEST"]:
                state_straight = "green"
            elif mode == "EW_LEFT" and dir_name in ["EAST", "WEST"]:
                state_left = "green"
                
            lane_configs.append({
                "lane_id": lane_id,
                "straight": {"state": state_straight, "duration": duration},
                "left": {"state": state_left, "duration": duration}
            })
        intersections.append({
            "intersection_id": i_id,
            "lanes": lane_configs
        })
    return intersections

def main():
    print(f"Connecting to MQTT Broker {BROKER}:{PORT}...")
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, "simple_controller")
    client.connect(BROKER, PORT)
    client.loop_start()
    print("Connected! Bắt đầu gửi tín hiệu điều khiển đèn...")

    phases = [
        ("NS_STRAIGHT", 15),
        ("ALL_RED", 2),
        ("NS_LEFT", 10),
        ("ALL_RED", 2),
        ("EW_STRAIGHT", 15),
        ("ALL_RED", 2),
        ("EW_LEFT", 10),
        ("ALL_RED", 2)
    ]
    
    phase_idx = 0
    cmd_count = 0
    try:
        while True:
            mode, duration = phases[phase_idx]
            cmd_id = f"cmd-{cmd_count:05d}"
            
            print(f"Chuyển pha: {mode} ({duration}s)")
            payload = get_intersections_payload(mode, duration)
            send_command(client, cmd_id, payload)
            
            time.sleep(duration)
            
            phase_idx = (phase_idx + 1) % len(phases)
            cmd_count += 1
    except KeyboardInterrupt:
        print("\nĐã dừng simple controller.")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
