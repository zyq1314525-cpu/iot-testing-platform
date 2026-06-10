"""
MQTT 协议自动化测试 — pytest 用例，验证 ESP32 与云端的 MQTT 通信协议。

被测对象:
    - 真实硬件: ESP32 WiFi+MQTT 固件（firmware/main/app_main.c）
    - CI 环境:  MQTT 设备模拟器（device_simulator/mqtt_simulator.py）
通信方式: MQTT（公共 broker broker.emqx.io）

前提:
    1. 真实硬件: ESP32 已烧好固件、连上 WiFi
    2. CI 环境: 模拟器已在后台运行（python device_simulator/mqtt_simulator.py &）
    3. broker.emqx.io 可访问（不需要注册/密码）

运行:
    # 全部 MQTT 测试（CI 或真实硬件）
    pytest tests/test_mqtt_protocol.py -v

    # 跳过遗嘱测试（真实硬件，固件未配 LWT）
    pytest tests/test_mqtt_protocol.py -v -k "not offline"

    # 只跑不需要硬件的用例
    pytest tests/test_mqtt_protocol.py -v -k "ping or ack"

固件/模拟器 MQTT 协议速查:
    ┌──────────────────┬────────────────────────────────────────────┐
    │ 事件              │ ESP32 → status topic 的 payload            │
    ├──────────────────┼────────────────────────────────────────────┤
    │ MQTT 连接成功     │ {"device_id":"ESP32-001","status":"online"}│
    │ 收到 PING         │ {"device_id":"ESP32-001","response":"PONG"}│
    │ 收到其他指令       │ {"device_id":"ESP32-001","response":"ACK",│
    │                   │  "cmd":"<原始指令>"}                        │
    │ 收到 RESET        │ 模拟器: 重新发布上线消息                       │
    │                   │ 真实固件: 回复 ACK（暂不支持 RESET 指令）    │
    │ 收到 DIE          │ 模拟器: os._exit(1) → broker 发布 LWT      │
    │                   │ LWT payload: {"device_id":"ESP32-001",     │
    │                   │              "status":"offline"}           │
    └──────────────────┴────────────────────────────────────────────┘
"""

import json
import os
import time
import pytest

# GitHub Actions 自动设置 CI=true
IN_CI = os.environ.get("CI", "").lower() == "true"


# ═══════════════════════════════════════════════════════════════════
# 测试 1：上线消息 — 设备 MQTT 连接后自动发布
# ═══════════════════════════════════════════════════════════════════
def test_device_online(mqtt_client):
    """
    设备 MQTT 连接后，应向 status topic 发布上线消息，
    格式: {"device_id":"ESP32-001","status":"online"}

    实现方式:
        - CI 模拟器: 发 RESET 指令 → 模拟器直接重新发布上线消息 →
          mqtt_client 在 broker 侧捕获。
        - 真实硬件: 固件目前不响应 RESET（会回复 ACK 被 drain 掉），
          本测试依赖模拟器。真实硬件如需验证上线消息格式，有以下选择：
            a) 给固件添加 RESET 指令支持（调用 esp_restart()）
            b) 手动给 ESP32 断电再上电，然后立即跑本用例
            c) 在 test_device_online 前先用串口 DTR 复位（需配合 serial_port fixture）

    断言:
        - device_id 字段为 "ESP32-001"
        - status 字段为 "online"
        - 整体为合法 JSON
    """
    # ① 清空旧消息
    mqtt_client.drain()

    # ② 发 RESET → 模拟器立即重新发布上线消息 → 直接等待接收
    #    注意: 不在这里 drain，否则会把刚收到的上线消息清掉
    mqtt_client.publish_cmd("RESET")
    raw = mqtt_client.wait_reply(timeout=5.0)
    assert raw is not None, (
        "❌ 超时: 发 RESET 后 15s 内未收到上线消息。\n"
        "   CI 环境: 检查模拟器是否在后台运行（python device_simulator/mqtt_simulator.py &）\n"
        "   真实硬件: 固件暂不支持 RESET 指令，请用 DTR 复位或跳过本用例"
    )

    # ⑤ 解析 JSON 并断言
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(
            f"❌ 上线消息不是合法 JSON:\n"
            f"   原始内容: {raw}"
        )

    assert data.get("device_id") == "ESP32-001", (
        f"❌ device_id 不符，期望 ESP32-001\n"
        f"   实际 JSON: {data}"
    )
    assert data.get("status") == "online", (
        f"❌ status 不符，期望 online\n"
        f"   实际 JSON: {data}"
    )

    print(f"\n   ✅ 上线消息正确: {data}")


# ═══════════════════════════════════════════════════════════════════
# 测试 2：PING/PONG — 心跳探测
# ═══════════════════════════════════════════════════════════════════
def test_ping_pong(mqtt_client):
    """
    向设备 cmd topic 发送 "PING"，断言回复 PONG。

    固件/模拟器逻辑:
        if payload == "PING":
            publish {"device_id":"ESP32-001","response":"PONG"}

    断言:
        - 能收到回复（非空）
        - response 字段为 "PONG"
        - device_id 字段为 "ESP32-001"
    """
    mqtt_client.drain()

    mqtt_client.publish_cmd("PING")

    raw = mqtt_client.wait_reply(timeout=5.0)
    assert raw is not None, (
        "❌ 超时: 发 PING 后 5s 内未收到回复。\n"
        "   CI 环境: 模拟器是否还在运行？\n"
        "   真实硬件: ESP32 是否在线？MQTT broker 是否可达？"
    )

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
    向设备发自定义指令（非 PING），断言回复 ACK 且 cmd 回显正确。

    固件/模拟器逻辑:
        非 PING 指令 → publish {"device_id":"ESP32-001",
                                "response":"ACK",
                                "cmd":"<原指令>"}

    断言:
        - response 字段为 "ACK"
        - cmd 字段回显发送的指令原文
        - device_id 字段为 "ESP32-001"
    """
    CMD = "SET_REPORT_INTERVAL"

    mqtt_client.drain()

    mqtt_client.publish_cmd(CMD)

    raw = mqtt_client.wait_reply(timeout=5.0)
    assert raw is not None, (
        f"❌ 超时: 发 '{CMD}' 后 5s 内未收到 ACK。"
    )

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
# 测试 4：遗嘱消息 — 设备异常断线后 broker 发布 LWT
# ═══════════════════════════════════════════════════════════════════
#
# 双环境策略:
#   - CI 模拟器: 已配置 LWT + 响应 DIE 指令（os._exit 异常退出）
#     → 本用例在 CI 中直接跑通 ✅
#   - 真实硬件: 固件未配置 LWT（app_main.c mqtt_cfg 缺少 .session.last_will）
#     → 本用例 skip，等固件改动后取消
#
# 固件改动方案（后续做）:
#   esp_mqtt_client_config_t mqtt_cfg = {
#       .broker.address.uri = MQTT_BROKER,
#       .session.last_will = {
#           .topic  = MQTT_TOPIC_STATUS,
#           .msg    = "{\"device_id\":\"ESP32-001\",\"status\":\"offline\"}",
#           .qos    = 1,
#           .retain = 0,
#       },
#   };
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.skipif(
    not IN_CI,
    reason="TODO: 真实固件需先配置 MQTT Last Will Testament（遗嘱消息）"
)
def test_offline(mqtt_client):
    """
    异常断线时，broker 应发布遗嘱消息，payload 含 status=offline。

    CI 实现: 发 DIE 指令 → 模拟器 os._exit(1) 立即退出 →
            TCP 连接异常断开 → broker 检测到 → 发布 LWT →
            mqtt_client 收到 {"device_id":"ESP32-001","status":"offline"}

    ⚠️  本用例必须放在最后执行（conftest.py 通过
        pytest_collection_modifyitems 保证），因为它会终止模拟器进程。
    """
    # ① 先发 PING 确认设备在线
    mqtt_client.drain()
    mqtt_client.publish_cmd("PING")
    ping_reply = mqtt_client.wait_reply(timeout=5.0)
    assert ping_reply is not None, (
        "❌ 设备不在线，无法测试遗嘱消息。\n"
        "   CI 环境: 模拟器是否在运行？"
    )
    print(f"   ✅ 设备在线确认: {ping_reply}")

    # ② 清空收件箱，准备好捕获遗嘱消息
    mqtt_client.drain()

    # ③ 发送 DIE 指令 → 模拟器立即 os._exit(1)
    #    不经过 MQTT DISCONNECT → broker 检测 TCP 断开 → 发布 LWT
    mqtt_client.publish_cmd("DIE")

    # ④ 等待遗嘱消息（broker 通常需要几秒检测 TCP 超时）
    raw = mqtt_client.wait_reply(timeout=12.0)
    assert raw is not None, (
        "❌ 超时: 设备断线后 12s 内未收到遗嘱消息。\n"
        "   broker 可能需要更长时间检测断线，或 LWT 未正确配置。"
    )

    # ⑤ 解析并断言遗嘱消息格式
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise AssertionError(
            f"❌ 遗嘱消息不是合法 JSON:\n"
            f"   原始内容: {raw}"
        )

    assert data.get("device_id") == "ESP32-001", (
        f"❌ 遗嘱消息 device_id 不符\n"
        f"   实际 JSON: {data}"
    )
    assert data.get("status") == "offline", (
        f"❌ 遗嘱消息 status 应为 offline\n"
        f"   实际 JSON: {data}"
    )

    print(f"\n   ✅ 遗嘱消息正确: {data}")
