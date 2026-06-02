#include <stdio.h>
#include <string.h>

// ========== 1. 定义结构体（模拟一个温湿度传感器设备）==========
typedef struct {
    char  device_id[16];   // 设备ID
    float temperature;   // 温度
    float humidity;      // 湿度
    int   status;        // 0=离线, 1=在线
} DeviceInfo;

int main() {
    // ========== 2. 创建结构体变量（栈上分配）==========
    DeviceInfo sensor = {
        .device_id = "TEMP_001",
        .temperature = 25.5,
        .humidity = 60.0,
        .status = 1
    };

    // ========== 3. 用指针修改温度值（核心！）==========
    DeviceInfo *p = &sensor;  // p 指向 sensor 的地址

    // 两种写法，效果一样：
    p->temperature = 30.2;           // 箭头访问（推荐，一眼看出是指针）
    (*p).humidity = 55.0;            // 解引用后点访问（等价写法）

    // ========== 4. 打印验证 ==========
    printf("=== 设备信息 ===\n");
    printf("设备ID: %s\n", p->device_id);
    printf("温度:   %.1f °C\n", p->temperature);
    printf("湿度:   %.1f %%\n", p->humidity);
    printf("状态:   %s\n", p->status == 1 ? "在线" : "离线");

    // ========== 5. 嵌入式常见场景：指针遍历结构体数组 ==========
    printf("\n=== 批量设备测试 ===\n");
    DeviceInfo devices[3] = {
        {"DEV_001", 20.0, 50.0, 1},
        {"DEV_002", 22.5, 55.0, 1},
        {"DEV_003", 35.0, 40.0, 0}  // 这个温度异常
    };

    for (int i = 0; i < 3; i++) {
        DeviceInfo *d = &devices[i];  // 取第i个元素的地址
        printf("[%s] 温度=%.1f, 状态=%s\n", 
               d->device_id, 
               d->temperature,
               d->temperature > 30.0 ? "⚠️ 超温!" : "正常");
    }

    return 0;
}