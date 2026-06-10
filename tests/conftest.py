"""
pytest 配置文件 — 自动发现 ESP32 串口，提供串口和 MQTT 两种通信 fixture。

用法：
    pytest tests/ -v                          # 自动扫描，找到就测
    pytest tests/ -v -k "serial"              # 只跑串口用例
    pytest tests/ -v -k "mqtt"               # 只跑 MQTT 用例
"""

import os
import time
import queue
import pytest
import serial
import serial.tools.list_ports
import paho.mqtt.client as mqtt


BAUDRATE = 115200
TIMEOUT = 1.0

# ========== MQTT 公共配置 ==========
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_TOPIC_CMD = "iot/test/device001/cmd"
MQTT_TOPIC_STATUS = "iot/test/device001/status"

# ESP32 常用的 USB 转串口芯片名称关键字
ESP32_CHIP_KEYWORDS = ["CH340", "CP210", "CP210x", "Silicon Labs", "FT232", "ESP32"]


def find_esp32_port():
    """自动扫描所有可用串口，找第一个疑似 ESP32 的端口。"""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description
        for keyword in ESP32_CHIP_KEYWORDS:
            if keyword.lower() in desc.lower():
                return p.device
    return None


# 优先级：环境变量 ESP32_PORT > 自动扫描
ESP32_PORT = os.environ.get("ESP32_PORT") or find_esp32_port()

if ESP32_PORT is None:
    raise RuntimeError(
        "❌ 没找到 ESP32 串口。\n"
        "   请确认 ESP32 已插上，设备管理器里有 COM 口。\n"
        "   或手动指定: set ESP32_PORT=COM8 && pytest tests/ -v"
    )

print(f"\n🔌 ESP32 串口: {ESP32_PORT}")


# ========== 串口辅助 ==========

def send_at(ser, cmd, wait=0.3):
    """发一条 AT 指令，等 ESP32 回复，把收到的所有字节当字符串返回。"""
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode("utf-8"))
    time.sleep(wait)
    raw = ser.read(ser.in_waiting or 1)
    return raw.decode("utf-8", errors="replace").strip()


@pytest.fixture(scope="function")
def serial_port():
    """串口 fixture — 每次测试前打开串口，测完自动关闭。"""
    ser = serial.Serial(
        port=ESP32_PORT,
        baudrate=BAUDRATE,
        timeout=TIMEOUT,
    )
    time.sleep(0.5)
    ser.reset_input_buffer()

    yield ser

    ser.close()


# ========== MQTT 辅助 ==========

class MqttHelper:
    """
    封装 MQTT 客户端，测试用例用它发指令、收回复。

    用法：
        mqtt = MqttHelper()
        mqtt.publish_cmd("PING")
        reply = mqtt.wait_reply(timeout=3)
        assert reply is not None and "PONG" in reply
    """

    def __init__(self):
        self._inbox = queue.Queue()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

        self._client.connect(MQTT_BROKER, MQTT_PORT, 60)
        self._client.loop_start()
        time.sleep(0.5)

    def _on_connect(self, client, userdata, flags, rc, props=None):
        if rc == 0:
            client.subscribe(MQTT_TOPIC_STATUS)
            print(f"   📡 MQTT 已连接 {MQTT_BROKER}，订阅 {MQTT_TOPIC_STATUS}")

    def _on_message(self, client, userdata, msg):
        self._inbox.put(msg.payload.decode())

    def publish_cmd(self, payload: str):
        """向 ESP32 的 cmd 主题发一条指令。"""
        self._client.publish(MQTT_TOPIC_CMD, payload)

    def wait_reply(self, timeout=3.0):
        """等 ESP32 回复，超时返回 None。"""
        try:
            return self._inbox.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self):
        """清空收件箱里积压的旧消息。"""
        while not self._inbox.empty():
            try:
                self._inbox.get_nowait()
            except queue.Empty:
                break

    def close(self):
        self._client.loop_stop()
        self._client.disconnect()


@pytest.fixture(scope="function")
def mqtt_client():
    """
    MQTT fixture — 连公共 broker，测完自动断开。

    前提：ESP32 已连 WiFi 并运行 MQTT。
    """
    helper = MqttHelper()
    helper.drain()

    yield helper

    helper.close()
