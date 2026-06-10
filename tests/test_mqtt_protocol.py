"""
MQTT 协议自动化测试 — pytest 用例，验证 ESP32 与云端的 MQTT 通信协议。

被测对象: ESP32 WiFi+MQTT 固件（firmware/main/app_main.c）
通信方式: MQTT（公共 broker broker.emqx.io）

前提:
    1. ESP32 已烧好固件、连上 WiFi
    2. broker.emqx.io 可访问（不需要注册/密码）
    3. MQTT topic 与固件配置一致（device001）

运行:
    pytest tests/test_mqtt_protocol.py -v          # 只跑 MQTT 协议测试
    pytest tests/test_mqtt_protocol.py -v -k "online or ping or ack"  # 跳过遗嘱测试

固件 MQTT 协议速查（来自 app_main.c mqtt_event_handler）:
    ┌──────────────────┬────────────────────────────────────────────┐
    │ 事件              │ ESP32 → status topic 的 payload            │
    ├──────────────────┼────────────────────────────────────────────┤
    │ MQTT 连接成功     │ {"device_id":"ESP32-001","status":"online"}│
    │ 收到 PING         │ {"device_id":"ESP32-001","response":"PONG"}│
    │ 收到其他指令       │ {"device_id":"ESP32-001","response":"ACK",│
    │                   │  "cmd":"<原始指令>"}                        │
    │ 遗嘱消息 (LWT)     │ 未配置 → test_offline 标记为 TODO          │
    └──────────────────┴────────────────────────────────────────────┘
"""

import json
import time
import pytest


# ═══════════════════════════════════════════════════════════════════
# 测试 1：上线消息 — ESP32 MQTT 连接后自动发布
# ═══════════════════════════════════════════════════════════════════
def test_device_online(serial_port, mqtt_client):
    """
    ESP32 上电 / MQTT 连接后，应向 status topic 发布上线消息，
    格式: {"device_id":"ESP32-001","status":"online"}

    实现方式:
        通过串口 DTR 引脚触发 ESP32 硬件复位 → ESP32 重启 →
        重新连 WiFi → 重新连 MQTT → 自动发布上线消息 →
        mqtt_client 在 broker 侧捕获。

    断言:
        - device_id 字段存在且值为 "ESP32-001"
        - status 字段存在且值为 "online"
    """
    # ① 清空 MQTT 收件箱里可能残留的旧消息
    mqtt_client.drain()

    # ② 通过 DTR 引脚触发 ESP32 硬件复位
    #    ESP32 开发板的 EN 引脚通过电容耦合到 DTR，拉低→释放 = 复位脉冲
    serial_port.dtr = False
    time.sleep(0.1)
    serial_port.dtr = True
    time.sleep(0.5)          # 等 ESP32 进入 bootloader 再跳到 app

    # ③ 等待 ESP32 完成: 启动(~0.5s) + WiFi 连接(~3-5s) + MQTT 连接 + 发布上线消息
    #    给 25 秒超时，覆盖网络慢的情况
    raw = mqtt_client.wait_reply(timeout=25.0)
    assert raw is not None, (
        "❌ 超时: ESP32 复位后 25s 内未收到上线消息。\n"
        "   可能原因: WiFi 密码改了 / broker 连不上 / DTR 复位未生效"
    )

    # ④ 解析 JSON 并断言
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(
            f"❌ 上线消息不是合法 JSON:\n"
            f"   原始内容: {raw}"
        )

    assert "device_id" in data, (
        f"❌ 上线消息缺少 device_id 字段\n"
        f"   实际 JSON: {data}"
    )
    assert data["device_id"] == "ESP32-001", (
        f"❌ device_id 不符，期望 ESP32-001\n"
        f"   实际: {data.get('device_id')}"
    )
    assert "status" in data, (
        f"❌ 上线消息缺少 status 字段\n"
        f"   实际 JSON: {data}"
    )
    assert data["status"] == "online", (
        f"❌ status 不符，期望 online\n"
        f"   实际: {data.get('status')}"
    )

    print(f"\n   ✅ 上线消息正确: {data}")


# ═══════════════════════════════════════════════════════════════════
# 测试 2：PING/PONG — 心跳探测
# ═══════════════════════════════════════════════════════════════════
def test_ping_pong(mqtt_client):
    """
    向 ESP32 的 cmd topic 发送 "PING"，断言回复中包含 PONG。

    固件逻辑（app_main.c:124-127）:
        if strncmp(event->data, "PING", ...) == 0:
            publish "{"device_id":"ESP32-001","response":"PONG"}"

    断言:
        - 能收到回复（非空）
        - response 字段为 "PONG"
        - device_id 字段为 "ESP32-001"
    """
    # ① 清理旧消息，避免读到上次测试的残留
    mqtt_client.drain()

    # ② 发送 PING 指令
    mqtt_client.publish_cmd("PING")

    # ③ 等待回复
    raw = mqtt_client.wait_reply(timeout=5.0)
    assert raw is not None, (
        "❌ 超时: 发 PING 后 5s 内未收到回复。\n"
        "   ESP32 是否在线？MQTT broker 是否可达？"
    )

    # ④ 解析并断言
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(
            f"❌ PING 回复不是合法 JSON:\n"
            f"   原始内容: {raw}"
        )

    assert data.get("response") == "PONG", (
        f"❌ 期望 response=PONG\n"
        f"   实际 JSON: {data}"
    )
    assert data.get("device_id") == "ESP32-001", (
        f"❌ device_id 不符\n"
        f"   实际 JSON: {data}"
    )

    print(f"\n   ✅ PING/PONG 正常: {data}")


# ═══════════════════════════════════════════════════════════════════
# 测试 3：自定义指令 ACK — 发指令，断言收到确认
# ═══════════════════════════════════════════════════════════════════
def test_command_ack(mqtt_client):
    """
    向 ESP32 发自定义指令（非 PING），断言回复 ACK 且 cmd 回显正确。

    固件逻辑（app_main.c:128-135）:
        非 PING 指令 → publish "{"device_id":"ESP32-001",
                                   "response":"ACK",
                                   "cmd":"<原指令>"}"

    断言:
        - response 字段为 "ACK"
        - cmd 字段回显发送的指令原文
        - device_id 字段为 "ESP32-001"
    """
    CMD = "SET_REPORT_INTERVAL"

    # ① 清理旧消息
    mqtt_client.drain()

    # ② 发送自定义指令
    mqtt_client.publish_cmd(CMD)

    # ③ 等待 ACK
    raw = mqtt_client.wait_reply(timeout=5.0)
    assert raw is not None, (
        f"❌ 超时: 发 '{CMD}' 后 5s 内未收到 ACK。"
    )

    # ④ 解析并断言
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(
            f"❌ ACK 回复不是合法 JSON:\n"
            f"   原始内容: {raw}"
        )

    assert data.get("response") == "ACK", (
        f"❌ 期望 response=ACK\n"
        f"   实际 JSON: {data}"
    )
    assert data.get("cmd") == CMD, (
        f"❌ cmd 回显不符\n"
        f"   期望: {CMD}\n"
        f"   实际: {data.get('cmd')}"
    )
    assert data.get("device_id") == "ESP32-001", (
        f"❌ device_id 不符\n"
        f"   实际 JSON: {data}"
    )

    print(f"\n   ✅ 指令 ACK 正常: {data}")


# ═══════════════════════════════════════════════════════════════════
# 测试 4：遗嘱消息 — ESP32 异常断线后 broker 发布 LWT
# ═══════════════════════════════════════════════════════════════════
#
# TODO: 当前固件未配置 MQTT Last Will Testament（遗嘱消息）。
#       需要在固件端做以下改动后，本条用例才能跑通：
#
#   1. app_main.c 的 mqtt_app_start() 中，在 esp_mqtt_client_init 之前
#      设置遗嘱消息:
#
#      esp_mqtt_client_config_t mqtt_cfg = {
#          .broker.address.uri = MQTT_BROKER,
#          .session.last_will = {
#              .topic = MQTT_TOPIC_STATUS,
#              .msg   = "{\"device_id\":\"ESP32-001\",\"status\":\"offline\"}",
#              .qos   = 1,
#              .retain = 0,
#          },
#      };
#
#   2. 重新编译烧录固件
#
#  测试逻辑（固件改动后启用）:
#     - ESP32 正常在线，mqtt_client 已订阅 status topic
#     - 通过串口 DTR 或物理断电使 ESP32 离线（不经过正常 MQTT DISCONNECT）
#     - broker 检测到 TCP 连接断开 → 自动发布遗嘱消息到 status topic
#     - mqtt_client 收到遗嘱消息: {"device_id":"ESP32-001","status":"offline"}
#     - 断言 device_id 和 status="offline"
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skip(reason="TODO: 固件需先配置 MQTT Last Will Testament（遗嘱消息），详见函数注释")
def test_offline(serial_port, mqtt_client):
    """
    异常断线时，broker 应发布遗嘱消息，payload 含 status=offline。

    当前固件未配置 LWT → 标记 skip，固件改动方案见上面 TODO 注释。
    """
    # ---- 固件完成 LWT 配置后，取消 skip 并实现以下逻辑 ----

    # ① 确认 ESP32 当前在线（发 PING 验证）
    mqtt_client.drain()
    mqtt_client.publish_cmd("PING")
    ping_reply = mqtt_client.wait_reply(timeout=5.0)
    assert ping_reply is not None, "❌ ESP32 不在线，无法测试遗嘱消息"

    # ② 清空收件箱，准备捕获遗嘱消息
    mqtt_client.drain()

    # ③ 通过 DTR 拉低使 ESP32 复位（模拟异常断线，EN 引脚拉低后 ESP32 直接断电）
    #    注意：不能用 MQTT DISCONNECT（那是正常断线，不会触发 LWT）
    serial_port.dtr = False
    time.sleep(0.5)  # 保持复位状态，确保 broker 检测到 TCP 断开

    # ④ broker 检测到连接断开后，应发布遗嘱消息
    raw = mqtt_client.wait_reply(timeout=10.0)
    assert raw is not None, (
        "❌ 超时: ESP32 断线后 10s 内未收到遗嘱消息。\n"
        "   检查固件是否已配置 LWT"
    )

    # ⑤ 解析并断言遗嘱消息格式
    data = json.loads(raw)
    assert data.get("device_id") == "ESP32-001", (
        f"❌ 遗嘱消息 device_id 不符: {data}"
    )
    assert data.get("status") == "offline", (
        f"❌ 遗嘱消息 status 应为 offline: {data}"
    )

    print(f"\n   ✅ 遗嘱消息正确: {data}")
