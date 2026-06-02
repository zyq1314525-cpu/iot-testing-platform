#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "driver/uart.h"
#include "esp_log.h"

// ========== 配置 ==========
#define UART_NUM        UART_NUM_0      // 用 UART0（USB 串口）
#define BUF_SIZE        1024            // 接收缓冲区
#define TAG             "IOT_TEST"      // 日志标签

// ========== 函数：初始化串口 ==========
static void uart_init(void) {
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity    = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
    };

    // 配置串口参数
    uart_param_config(UART_NUM, &uart_config);
    
    // 安装驱动（不指定引脚，用默认的 TX=GPIO1, RX=GPIO3）
    uart_driver_install(UART_NUM, BUF_SIZE * 2, 0, 0, NULL, 0);
}

// ========== 函数：发送回复 ==========
static void send_response(const char *data) {
    uart_write_bytes(UART_NUM, data, strlen(data));
    ESP_LOGI(TAG, "发送: %s", data);
}

// ========== 主任务：读取并处理 AT 指令 ==========
static void uart_task(void *pvParameters) {
    uint8_t data[BUF_SIZE];
    char rx_buffer[128];   // 累积收到的字符串
    int rx_len = 0;

    while (1) {
        // 读取串口数据（阻塞，最多等 100ms）
        int len = uart_read_bytes(UART_NUM, data, BUF_SIZE - 1, 100 / portTICK_PERIOD_MS);

        if (len > 0) {
            data[len] = '\0';  // 加结束符，方便当字符串处理
            ESP_LOGI(TAG, "收到: %s", data);

            // 简单处理：把收到的内容追加到缓冲区
            // 实际应该做帧边界检测（等 \r\n），这里简化
            if (strncmp((char *)data, "AT\r\n", 4) == 0) {
                send_response("OK\r\n");
            }
            else if (strncmp((char *)data, "AT+INFO\r\n", 9) == 0) {
                char info[64];
                snprintf(info, sizeof(info), 
                         "DEVICE:ESP32,FW:v1.0,UPTIME:%lu\r\n", 
                         (unsigned long)(xTaskGetTickCount() / 100));
                send_response(info);
            }
            else if (strncmp((char *)data, "AT+", 3) == 0) {
                send_response("ERROR:UNKNOWN_CMD\r\n");
            }
        }
    }
}

// ========== 程序入口 ==========
void app_main(void) {
    ESP_LOGI(TAG, "IoT Testing Platform 启动");

    uart_init();

    // 创建串口处理任务
    xTaskCreate(uart_task, "uart_task", 2048, NULL, 10, NULL);
}