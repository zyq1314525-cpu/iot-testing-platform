#include <stdio.h>
#include <string.h>

// ========== 函数：解析 AT 指令 ==========
// 输入: "AT+STATUS\r\n"  ->  输出: "STATUS"
// 输入: "AT+INFO\r\n"    ->  输出: "INFO"
// 返回值: 0=成功, -1=格式错误
int parse_at_command(const char *input, char *cmd_out, int cmd_buf_size) {
    // 1. 检查是否以 "AT+" 开头
    if (strncmp(input, "AT+", 3) != 0) {
        return -1;  // 不是 AT+ 开头
    }

    // 2. 找到 '+' 后面的指令名起始位置
    const char *cmd_start = input + 3;

    // 3. 找到 \r 或 \n 结束位置
    int len = 0;
    while (cmd_start[len] != '\0' && cmd_start[len] != '\r' && cmd_start[len] != '\n') {
        len++;
    }

    // 4. 检查缓冲区够不够
    if (len >= cmd_buf_size) {
        return -1;  // 缓冲区太小
    }

    // 5. 拷贝结果
    strncpy(cmd_out, cmd_start, len);
    cmd_out[len] = '\0';  // 手动加结束符

    return 0;
}

// ========== 主函数：测试 ==========
int main() {
    // 测试数据（模拟串口收到的数据）
    const char *test1 = "AT+STATUS\r\n";
    const char *test2 = "AT+INFO\r\n";
    const char *test3 = "AT+SETTEMP=25.5\r\n";  // 带参数的版本
    const char *test4 = "ERROR\r\n";             // 错误格式

    char cmd[32];  // 放解析出来的指令名

    printf("=== AT 指令解析测试 ===\n\n");

    // 测试 1
    if (parse_at_command(test1, cmd, sizeof(cmd)) == 0) {
        printf("收到: [%s] -> 指令: [%s]\n", test1, cmd);
    } else {
        printf("收到: [%s] -> 解析失败\n", test1);
    }

    // 测试 2
    if (parse_at_command(test2, cmd, sizeof(cmd)) == 0) {
        printf("收到: [%s] -> 指令: [%s]\n", test2, cmd);
    }

    // 测试 3：带参数的进阶版（只取等号前面的指令名）
    printf("\n=== 进阶：带参数的指令 ===\n");
    char *equal_pos = strchr(test3, '=');
    if (equal_pos != NULL) {
        int cmd_len = equal_pos - (test3 + 3);  // 计算指令名长度
        strncpy(cmd, test3 + 3, cmd_len);
        cmd[cmd_len] = '\0';
        printf("收到: [%s] -> 指令: [%s], 参数: [%s]\n", 
               test3, cmd, equal_pos + 1);
    }

    // 测试 4：错误格式
    printf("\n=== 错误格式测试 ===\n");
    if (parse_at_command(test4, cmd, sizeof(cmd)) != 0) {
        printf("收到: [%s] -> 拒绝: 不是AT指令\n", test4);
    }

    return 0;
}