#include <stdio.h>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_log.h"
#include "esp_random.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_netif.h"
#include "nvs_flash.h"
#include "mqtt_client.h"

// ========== WiFi 配置（改成你的手机热点）==========
#define WIFI_SSID       "qing"     // ← 烧录前改这里
#define WIFI_PASS       "goodwifi@"       // ← 烧录前改这里
#define WIFI_MAX_RETRY   5                    // 最多重试 5 次

// ========== MQTT 配置 ==========
#define MQTT_BROKER     "mqtt://broker.emqx.io:1883"  // 公共测试 broker
#define MQTT_TOPIC_STATUS   "iot/test/device001/status"  // 上线消息发这里
#define MQTT_TOPIC_CMD      "iot/test/device001/cmd"     // 订阅指令

// ========== 其他 ==========
#define BUF_SIZE        128
#define TAG             "IOT_TEST"
#define TAG_WIFI        "WIFI"
#define TAG_MQTT        "MQTT"

// ========== 全局句柄 ==========
static esp_mqtt_client_handle_t mqtt_client = NULL;  // MQTT 客户端句柄
static EventGroupHandle_t wifi_event_group;           // WiFi 事件组
static const int WIFI_CONNECTED_BIT = BIT0;           // WiFi 连接成功标志位

// ========== UART（保留你之前的 AT 指令处理，不动）==========

static void strip_newline(char *str) {
    int len = strlen(str);
    while (len > 0 && (str[len-1] == '\r' || str[len-1] == '\n')) {
        str[len-1] = '\0';
        len--;
    }
}

static void uart_task(void *pvParameters) {
    char line[BUF_SIZE];
    ESP_LOGI(TAG, "等待指令...");

    while (1) {
        if (fgets(line, sizeof(line), stdin) == NULL) {
            vTaskDelay(pdMS_TO_TICKS(100));
            continue;
        }

        strip_newline(line);
        if (strlen(line) == 0) continue;

        ESP_LOGI(TAG, "收到: %s", line);

        if (strcmp(line, "AT") == 0) {
            printf("OK\r\n");
            ESP_LOGI(TAG, "发送: OK");
        }
        else if (strcmp(line, "AT+INFO") == 0) {
            printf("DEVICE:ESP32,FW:v1.1,UPTIME:%lu\r\n",
                   (unsigned long)(xTaskGetTickCount() * portTICK_PERIOD_MS / 1000));
            ESP_LOGI(TAG, "发送: 设备信息");
        }
        else if (strcmp(line, "AT+STATUS") == 0) {
            float temp = 25.0f + (esp_random() % 100) / 10.0f;
            float hum  = 50.0f + (esp_random() % 100) / 10.0f;
            printf("+STATUS:T=%.1f,H=%.1f\r\n", temp, hum);
            ESP_LOGI(TAG, "发送: STATUS T=%.1f H=%.1f", temp, hum);
        }
        else if (strncmp(line, "AT+", 3) == 0) {
            printf("ERROR:UNKNOWN_CMD\r\n");
            ESP_LOGI(TAG, "发送: ERROR");
        }
        else {
            ESP_LOGI(TAG, "忽略: 非AT指令");
        }
    }
}

// ========== MQTT 事件处理 ==========

static void mqtt_event_handler(void *handler_args, esp_event_base_t base,
                               int32_t event_id, void *event_data) {
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;

    switch ((esp_mqtt_event_id_t)event_id) {

        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG_MQTT, "已连接 broker: %s", MQTT_BROKER);

            // ① 发送上线消息
            {
                const char *online_msg = "{\"device_id\":\"ESP32-001\",\"status\":\"online\"}";
                int msg_id = esp_mqtt_client_publish(
                    mqtt_client, MQTT_TOPIC_STATUS, online_msg, 0, 1, 0);
                ESP_LOGI(TAG_MQTT, "发布上线消息 [topic=%s] msg_id=%d",
                         MQTT_TOPIC_STATUS, msg_id);
            }

            // ② 订阅指令主题
            {
                int msg_id = esp_mqtt_client_subscribe(mqtt_client, MQTT_TOPIC_CMD, 0);
                ESP_LOGI(TAG_MQTT, "订阅主题 [%s] msg_id=%d",
                         MQTT_TOPIC_CMD, msg_id);
            }
            break;

        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG_MQTT, "MQTT 断开连接");
            break;

        case MQTT_EVENT_DATA:
            // 收到云端下发的指令
            ESP_LOGI(TAG_MQTT, "收到指令: topic=%.*s, payload=%.*s",
                     event->topic_len, event->topic,
                     event->data_len, event->data);

            // 处理指令：如果是 "PING" 回复 "PONG"，其他回复 ACK
            if (strncmp(event->data, "PING", event->data_len) == 0) {
                esp_mqtt_client_publish(mqtt_client, MQTT_TOPIC_STATUS,
                    "{\"device_id\":\"ESP32-001\",\"response\":\"PONG\"}", 0, 1, 0);
                ESP_LOGI(TAG_MQTT, "回复: PONG");
            } else {
                char ack[128];
                snprintf(ack, sizeof(ack),
                    "{\"device_id\":\"ESP32-001\",\"response\":\"ACK\","
                    "\"cmd\":\"%.*s\"}",
                    event->data_len, event->data);
                esp_mqtt_client_publish(mqtt_client, MQTT_TOPIC_STATUS, ack, 0, 1, 0);
                ESP_LOGI(TAG_MQTT, "回复: ACK");
            }
            break;

        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG_MQTT, "MQTT 错误");
            break;

        default:
            break;
    }
}

// ========== WiFi 事件处理 ==========

static void wifi_event_handler(void *arg, esp_event_base_t event_base,
                               int32_t event_id, void *event_data) {
    static int retry_count = 0;

    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        // WiFi 模块启动完成 → 开始连接热点
        esp_wifi_connect();
        ESP_LOGI(TAG_WIFI, "正在连接 %s ...", WIFI_SSID);
    }
    else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        // WiFi 断开 → 重试
        if (retry_count < WIFI_MAX_RETRY) {
            esp_wifi_connect();
            retry_count++;
            ESP_LOGW(TAG_WIFI, "断开，重试第 %d 次...", retry_count);
        } else {
            ESP_LOGE(TAG_WIFI, "重试 %d 次失败，放弃", WIFI_MAX_RETRY);
        }
    }
    else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        // 拿到 IP → 标记连接成功
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG_WIFI, "WiFi 已连接! IP: " IPSTR, IP2STR(&event->ip_info.ip));
        retry_count = 0;
        xEventGroupSetBits(wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

// ========== 初始化 WiFi（STA 模式）==========

static void wifi_init_sta(void) {
    wifi_event_group = xEventGroupCreate();

    // 初始化 TCP/IP 协议栈
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();  // 创建 WiFi STA 接口

    // 注册事件回调
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL, NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL, NULL));

    // 配置 WiFi
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    wifi_config_t wifi_config = {
        .sta = {
            .ssid = WIFI_SSID,
            .password = WIFI_PASS,
        },
    };
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG_WIFI, "WiFi STA 初始化完成");
}

// ========== 启动 MQTT 客户端 ==========

static void mqtt_app_start(void) {
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker.address.uri = MQTT_BROKER,
    };
    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID,
                                   mqtt_event_handler, NULL);
    esp_mqtt_client_start(mqtt_client);
    ESP_LOGI(TAG_MQTT, "MQTT 客户端已启动");
}

// ========== 程序入口 ==========

void app_main(void) {
    ESP_LOGI(TAG, "IoT Testing Platform 启动 v1.1");
    ESP_LOGI(TAG, "UART AT 指令就绪，输入 AT 或 AT+INFO");

    // 1. 初始化 NVS（WiFi 需要）
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES ||
        ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    // 2. 启动 UART AT 指令任务（立即就绪，不依赖 WiFi）
    xTaskCreate(uart_task, "uart_task", 4096, NULL, 5, NULL);

    // 3. 初始化 WiFi
    wifi_init_sta();

    // 4. 等待 WiFi 连接成功
    EventBits_t bits = xEventGroupWaitBits(
        wifi_event_group,
        WIFI_CONNECTED_BIT,
        pdFALSE,        // 不清除标志位
        pdTRUE,         // 等所有位都置上
        portMAX_DELAY   // 一直等到连上
    );

    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "WiFi 连接成功，启动 MQTT...");
        // 5. WiFi 连上后再启动 MQTT
        mqtt_app_start();
    }

    // app_main 结束，UART 任务和 MQTT 客户端在后台继续运行
}
