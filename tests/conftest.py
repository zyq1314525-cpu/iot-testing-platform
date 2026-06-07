"""
pytest 配置文件 — 自动发现 ESP32 串口，提供 serial_port fixture 和 send_at 辅助函数。

用法：
    pytest tests/ -v                          # 自动扫描，找到就测
    set ESP32_PORT=COM8 && pytest tests/ -v   # 手动指定（跳过自动扫描）
"""

import os
import time
import pytest
import serial
import serial.tools.list_ports


BAUDRATE = 115200
TIMEOUT = 1.0

# ESP32 常用的 USB 转串口芯片名称关键字（大小写不敏感）
ESP32_CHIP_KEYWORDS = ["CH340", "CP210", "CP210x", "Silicon Labs", "FT232", "ESP32"]


def find_esp32_port():
    """
    自动扫描所有可用串口，找第一个疑似 ESP32 的端口。

    Returns:
        端口名（如 "COM8"），找不到返回 None。
    """
    ports = serial.tools.list_ports.comports()
    for p in ports:
        # p.description 一般长这样: "USB-SERIAL CH340 (COM8)"
        desc = p.description
        for keyword in ESP32_CHIP_KEYWORDS:
            if keyword.lower() in desc.lower():
                return p.device  # 如 "COM8"
    return None


# 优先级：环境变量 ESP32_PORT > 自动扫描
ESP32_PORT = os.environ.get("ESP32_PORT") or find_esp32_port()

if ESP32_PORT is None:
    raise RuntimeError(
        "❌ 没找到 ESP32 串口。\n"
        "   请确认 ESP32 已插上，设备管理器里有 COM 口。\n"
        "   或手动指定: set ESP32_PORT=COM8 && pytest tests/ -v"
    )

# 模块加载时打印，让用户知道连到了哪个口
print(f"\n🔌 ESP32 串口: {ESP32_PORT}")


def send_at(ser, cmd, wait=0.3):
    """
    发一条 AT 指令，等 ESP32 回复，把收到的所有字节当字符串返回。
    """
    ser.reset_input_buffer()
    ser.write((cmd + "\r\n").encode("utf-8"))
    time.sleep(wait)
    raw = ser.read(ser.in_waiting or 1)
    return raw.decode("utf-8", errors="replace").strip()


@pytest.fixture(scope="function")
def serial_port():
    """每次测试前打开串口，测完自动关闭。"""
    ser = serial.Serial(
        port=ESP32_PORT,
        baudrate=BAUDRATE,
        timeout=TIMEOUT,
    )
    time.sleep(0.5)
    ser.reset_input_buffer()

    yield ser

    ser.close()
