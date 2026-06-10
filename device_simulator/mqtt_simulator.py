"""
MQTT 设备模拟器 — 在软件层面完整模拟 ESP32 的 MQTT 协议行为。
用于 CI 环境替代真实 ESP32 硬件。

模拟行为（与 firmware/main/app_main.c 的 mqtt_event_handler 完全对应）:
    ┌──────────────────────┬──────────────────────────────────────────┐
    │ 触发条件              │ 模拟器行为                                │
    ├──────────────────────┼──────────────────────────────────────────┤
    │ MQTT 连接成功         │ publish {"device_id":"ESP32-001",        │
    │                      │          "status":"online"}              │
    │ 收到 "PING"          │ publish {"device_id":"ESP32-001",        │
    │                      │          "response":"PONG"}              │
    │ 收到其他指令          │ publish {"device_id":"ESP32-001",        │
    │                      │          "response":"ACK",               │
    │                      │          "cmd":"<原指令>"}               │
    │ 收到 "RESET"         │ 重新发布上线消息（等效于硬件复位后重连）     │
    │ 收到 "DIE"           │ os._exit(1) 异常退出 → broker 发布 LWT   │
    │ 异常断线              │ LWT: {"device_id":"ESP32-001",           │
    │                      │        "status":"offline"}               │
    └──────────────────────┴──────────────────────────────────────────┘

用法:
    python device_simulator/mqtt_simulator.py          # 前台运行
    python device_simulator/mqtt_simulator.py &        # CI 后台运行
"""

import json
import os
import sys
import time
import paho.mqtt.client as mqtt

# ========== 配置（与 conftest.py 和固件 app_main.c 完全一致）==========
BROKER = "broker.emqx.io"
PORT = 1883
TOPIC_CMD = "iot/test/device001/cmd"
TOPIC_STATUS = "iot/test/device001/status"
DEVICE_ID = "ESP32-001"


def on_connect(client, userdata, flags, rc, props=None):
    """MQTT 连接成功 → 发布上线消息 + 订阅指令主题（对应固件 MQTT_EVENT_CONNECTED）"""
    if rc == 0:
        online_msg = json.dumps({"device_id": DEVICE_ID, "status": "online"})
        client.publish(TOPIC_STATUS, online_msg, qos=1)
        print(f"[SIM] 上线: {online_msg}", flush=True)

        client.subscribe(TOPIC_CMD, qos=0)
        print(f"[SIM] 订阅: {TOPIC_CMD}", flush=True)


def on_message(client, userdata, msg):
    """收到云端下发的指令 → 回复（对应固件 MQTT_EVENT_DATA）"""
    payload = msg.payload.decode()
    print(f"[SIM] 收到指令: {payload}", flush=True)

    if payload == "PING":
        # 对应固件 app_main.c:124-127
        reply = json.dumps({"device_id": DEVICE_ID, "response": "PONG"})
        client.publish(TOPIC_STATUS, reply, qos=1)
        print(f"[SIM] 回复: PONG", flush=True)

    elif payload == "RESET":
        # 测试基础设施指令：模拟硬件复位后重发上线消息
        # 不真断连（避免与 loop_forever 交互的竞态），直接重发等效
        online_msg = json.dumps({"device_id": DEVICE_ID, "status": "online"})
        client.publish(TOPIC_STATUS, online_msg, qos=1)
        print(f"[SIM] RESET — 重新发布上线消息: {online_msg}", flush=True)

    elif payload == "DIE":
        # 测试基础设施指令：模拟异常断电
        # os._exit 不经过 Python 清理，TCP 直接断开 → broker 发布 LWT
        print("[SIM] 收到 DIE — 模拟异常断电，触发 LWT", flush=True)
        time.sleep(0.2)
        os._exit(1)

    else:
        # 对应固件 app_main.c:128-135（非 PING 指令 → ACK）
        reply = json.dumps({
            "device_id": DEVICE_ID,
            "response": "ACK",
            "cmd": payload,
        })
        client.publish(TOPIC_STATUS, reply, qos=1)
        print(f"[SIM] 回复: ACK for '{payload}'", flush=True)


def on_disconnect(client, userdata, rc, props=None):
    """MQTT 断开（对应固件 MQTT_EVENT_DISCONNECTED）"""
    print(f"[SIM] MQTT 断开 (rc={rc})", flush=True)


def main():
    print(f"[SIM] MQTT 设备模拟器启动", flush=True)
    print(f"[SIM] 目标 broker: {BROKER}:{PORT}", flush=True)
    print(f"[SIM] 设备 ID: {DEVICE_ID}", flush=True)

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

    # 注册回调
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = on_disconnect

    # 配置遗嘱消息 LWT（对应固件待实现的 .session.last_will）
    # 当模拟器异常断线（os._exit / kill -9）时，broker 代为发布此消息
    lwt_payload = json.dumps({"device_id": DEVICE_ID, "status": "offline"})
    client.will_set(TOPIC_STATUS, lwt_payload, qos=1, retain=False)
    print(f"[SIM] LWT 已配置: {lwt_payload}", flush=True)

    # 连接 broker
    print(f"[SIM] 正在连接 {BROKER}:{PORT} ...", flush=True)
    client.connect(BROKER, PORT, 60)

    # 进入事件循环（阻塞，直到 os._exit 或 SIGTERM）
    client.loop_forever()


if __name__ == "__main__":
    main()
