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


# ═══════════════════════════════════════════════════════
# 测试 4：未知指令 — 断言回复 ERROR
# ═══════════════════════════════════════════════════════
def test_invalid_command(serial_port):
    """发 AT+FOO（固件不认识的指令），断言回复 ERROR"""
    reply = send_at(serial_port, "AT+FOO")

    assert "ERROR" in reply, (
        f"❌ 未知指令应回复 ERROR\n"
        f"   实际收到:\n{reply}"
    )


# ═══════════════════════════════════════════════════════
# 测试 5：空指令 — 断言固件不崩溃，能继续响应
# ═══════════════════════════════════════════════════════
def test_empty_command(serial_port):
    """发空行，断言固件不崩溃，之后仍能正常响应 AT"""
    # 连发 3 次空行
    for _ in range(3):
        send_at(serial_port, "")

    # 再发一条正常 AT，确认固件还活着
    reply = send_at(serial_port, "AT")
    assert "OK" in reply, (
        f"❌ 发空行后固件应仍能正常响应 AT\n"
        f"   实际收到:\n{reply}"
    )


# ═══════════════════════════════════════════════════════
# 测试 6：乱码 — 断言固件不崩溃，能继续响应
# ═══════════════════════════════════════════════════════
def test_no_response_garbage(serial_port):
    """发乱码，断言固件不卡死不崩溃，之后仍能响应正常指令"""
    # 模拟各种可能的乱码输入
    garbage_inputs = [
        "\x00\x01\x02",     # 不可打印的控制字符
        "??????",           # 无意义的符号串
        "AT\rAT\r\n",       # 畸形的指令拼接
    ]

    for junk in garbage_inputs:
        send_at(serial_port, junk)

    # 发正常 AT 确认固件还活着
    reply = send_at(serial_port, "AT")
    assert "OK" in reply, (
        f"❌ 发乱码后固件应仍能正常响应 AT\n"
        f"   实际收到:\n{reply}"
    )
