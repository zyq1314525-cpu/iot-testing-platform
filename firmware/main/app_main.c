#include <stdio.h>          // 标准输入输出库，提供 printf、fgets 等函数
#include <string.h>         // 字符串处理库，提供 strlen、strncmp 等
#include "freertos/FreeRTOS.h"  // FreeRTOS 操作系统核心头文件（ESP32 自带的小型操作系统）
#include "freertos/task.h"      // FreeRTOS 任务管理，提供 vTaskDelay 等函数
#include "esp_log.h"            // ESP32 日志打印头文件
#include "esp_random.h"         // ESP32 硬件随机数生成器

// ========== 配置 ==========
#define BUF_SIZE        128             // 输入缓冲区大小（字节）
#define TAG             "IOT_TEST"      // 日志标签

// ========== 函数：去掉行尾的 \r 和 \n ==========
// fgets 会保留换行符，但不同终端发送的换行符不同（\n、\r\n、\r）
// 这个函数从字符串末尾把换行符全部抹掉，方便后面比较
static void strip_newline(char *str) {
    int len = strlen(str);                    // 获取字符串长度
    while (len > 0 && (str[len-1] == '\r' || str[len-1] == '\n')) {
        str[len-1] = '\0';                    // 把换行符替换成结束符
        len--;
    }
}

// ========== 主任务：读取并处理 AT 指令 ==========
static void uart_task(void *pvParameters) {
    char line[BUF_SIZE];  // 存放从串口读到的一行输入

    ESP_LOGI(TAG, "等待指令...");  // 只打印一次

    while (1) {
        // fgets: 从标准输入（stdin）读一行，阻塞等待用户输入
        if (fgets(line, sizeof(line), stdin) == NULL) {
            // 没读到数据时让出 CPU，避免看门狗超时
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        // 去掉行尾的 \r\n
        strip_newline(line);

        // 跳过空行（用户只按了回车）
        if (strlen(line) == 0) {
            continue;
        }

        ESP_LOGI(TAG, "收到: %s", line);

        // ----- AT 指令匹配 -----

        // AT：基本测试指令
        if (strcmp(line, "AT") == 0) {
            printf("OK\r\n");
            ESP_LOGI(TAG, "发送: OK");
        }
        // AT+INFO：查询设备信息
        else if (strcmp(line, "AT+INFO") == 0) {
            printf("DEVICE:ESP32,FW:v1.0,UPTIME:%lu\r\n",
                   (unsigned long)(xTaskGetTickCount() * portTICK_PERIOD_MS / 1000));
            ESP_LOGI(TAG, "发送: 设备信息");
        }
        // AT+STATUS：查询传感器数据（模拟温湿度读数）
        else if (strcmp(line, "AT+STATUS") == 0) {
            float temp = 25.0f + (esp_random() % 100) / 10.0f;  // 25.0 ~ 34.9
            float hum  = 50.0f + (esp_random() % 100) / 10.0f;  // 50.0 ~ 59.9
            printf("+STATUS:T=%.1f,H=%.1f\r\n", temp, hum);
            ESP_LOGI(TAG, "发送: STATUS T=%.1f H=%.1f", temp, hum);
        }
        // AT+ 开头的其他未知指令
        else if (strncmp(line, "AT+", 3) == 0) {
            printf("ERROR:UNKNOWN_CMD\r\n");
            ESP_LOGI(TAG, "发送: ERROR");
        }
        // 不以 AT 开头：忽略
        else {
            ESP_LOGI(TAG, "忽略: 非AT指令");
        }
    }
}

// ========== 程序入口 ==========
void app_main(void) {
    ESP_LOGI(TAG, "IoT Testing Platform 启动");
    ESP_LOGI(TAG, "输入 AT 或 AT+INFO 并回车，Ctrl+] 退出");

    // 不需要 uart_init，stdin/stdout 已由 ESP-IDF 自动初始化，直接开始监听
    xTaskCreate(uart_task, "uart_task", 4096, NULL, 5, NULL);
}