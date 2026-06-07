"""
MQTT 云端通信验证脚本 — 模拟云端给 ESP32 下指令，看回复。

前提：ESP32 已烧好 WiFi+MQTT 固件，正在运行且连着热点。
运行：python tests/mqtt_verify.py
"""

import time
import paho.mqtt.client as mqtt

BROKER = "broker.emqx.io"
PORT = 1883
TOPIC_CMD = "iot/test/device001/cmd"
TOPIC_STATUS = "iot/test/device001/status"


def on_connect(client, userdata, flags, rc):
    print(f"[连接] broker 返回码: {rc} (0=成功)")
    client.subscribe(TOPIC_STATUS)
    print(f"[订阅] {TOPIC_STATUS}")


def on_message(client, userdata, msg):
    print(f"\n>>> [收到 ESP32] topic={msg.topic}")
    print(f">>> payload={msg.payload.decode()}")


client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print(f"正在连接 {BROKER}:{PORT} ...")
client.connect(BROKER, PORT, 60)
client.loop_start()
time.sleep(1)  # 等连接建立 + 订阅生效

# ① 发 PING 指令
print(f"\n--- 发送 PING ---")
client.publish(TOPIC_CMD, "PING")
time.sleep(2)

# ② 发自定义指令（JSON 格式）
print(f"\n--- 发送 SET_REPORT_INTERVAL ---")
client.publish(TOPIC_CMD, "SET_REPORT_INTERVAL")
time.sleep(2)

# ③ 发另一条
print(f"\n--- 发送 REBOOT ---")
client.publish(TOPIC_CMD, "REBOOT")
time.sleep(2)

print("\n验证完成。按 Ctrl+C 退出。")
client.loop_stop()
client.disconnect()
