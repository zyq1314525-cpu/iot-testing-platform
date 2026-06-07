"""
AT 指令自动化测试 — pytest 一键跑完 3 条用例

被测对象: ESP32 AT 指令固件（firmware/main/app_main.c）
通信方式: USB 串口 115200 8N1

前提:
    1. ESP32 已烧好固件、USB 线连着电脑
    2. 设备管理器里确认 COM 号，终端里 set ESP32_PORT=COM8（或你的实际端口）
    3. 不能同时开 idf.py monitor（会占用串口，pytest 打不开）

运行:
    pytest tests/ -v
"""

import re
from conftest import send_at


# ═══════════════════════════════════════════════════════
# 测试 1：基本 AT — 确认 ESP32 在线
# ═══════════════════════════════════════════════════════
def test_at_ok(serial_port):
    """发 AT，断言回复中包含 OK"""
    reply = send_at(serial_port, "AT")

    assert "OK" in reply, (
        f"❌ 期望回复包含 OK\n"
        f"   实际收到:\n{reply}"
    )


# ═══════════════════════════════════════════════════════
# 测试 2：AT+INFO — 断言固件版本号
# ═══════════════════════════════════════════════════════
def test_at_info(serial_port):
    """发 AT+INFO，断言回复格式正确"""
    reply = send_at(serial_port, "AT+INFO")

    # 期望格式: DEVICE:ESP32,FW:v1.0,UPTIME:57
    pattern = r"DEVICE:ESP32,FW:v\d+\.\d+,UPTIME:\d+"
    assert re.search(pattern, reply), (
        f"❌ 期望回复格式: DEVICE:ESP32,FW:v版本号,UPTIME:秒数\n"
        f"   实际收到:\n{reply}"
    )


# ═══════════════════════════════════════════════════════
# 测试 3：AT+STATUS — 断言温湿度是数字且在合理范围
# ═══════════════════════════════════════════════════════
def test_at_status(serial_port):
    """发 AT+STATUS，断言 T=数字, H=数字 且数值合理"""
    reply = send_at(serial_port, "AT+STATUS")

    # 期望格式: +STATUS:T=26.3,H=57.0
    match = re.search(r"\+STATUS:T=([\d.]+),H=([\d.]+)", reply)
    assert match, (
        f"❌ 期望回复格式: +STATUS:T=温度,H=湿度\n"
        f"   实际收到:\n{reply}"
    )

    temp = float(match.group(1))
    hum = float(match.group(2))

    assert 20.0 <= temp <= 35.0, f"❌ 温度异常: {temp}°C"
    assert 40.0 <= hum <= 70.0,  f"❌ 湿度异常: {hum}%"

    print(f"\n   ✅ 温度={temp}°C, 湿度={hum}%")
