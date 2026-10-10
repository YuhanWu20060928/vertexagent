/* 鸡兔同笼（键盘输入版）
 *
 * 数学模型：
 *   设鸡 c 只，兔 r 只，则
 *       c + r     = heads   （头数方程）
 *       2c + 4r   = legs    （腿数方程）
 *   两式相减：2r = legs - 2*heads
 *     => 兔 r = (legs - 2*heads) / 2
 *     => 鸡 c = heads - r
 *
 * 有解的充要条件（非负整数解）：
 *   1) heads >= 0 且 legs >= 0
 *   2) legs - 2*heads 必须 >= 0 且为偶数
 *   3) 求出的鸡数 c 必须 >= 0
 *
 * 编译：gcc -std=c11 -Wall -Wextra -Wpedantic -O2 chicken_rabbit_input.c -o chicken_rabbit_input
 * 运行：./chicken_rabbit_input
 *       既支持每行一个数（先头数、后腿数），也支持一行写两个数，如 "35 94"
 *       输入非法时提示重输而不退出；Ctrl+Z（Windows）/ Ctrl+D（Linux）结束
 */

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <limits.h>

#define LINE_MAX_LEN 128            /* 单行输入缓冲长度 */

static int solve(int heads, int legs, int *chicken, int *rabbit);
static int parse_ints(const char *line, int *out, int max);
static int read_line(char *buf, size_t size);

/* 求解鸡兔同笼
 * heads : 总头数
 * legs  : 总腿数
 * *chicken / *rabbit : 输出参数，仅在返回 0 时有效
 * 返回 0 表示有解，-1 表示无解
 */
static int solve(int heads, int legs, int *chicken, int *rabbit)
{
    if (chicken == NULL || rabbit == NULL || heads < 0 || legs < 0) {
        return -1;
    }

    if (heads > legs / 2) {           /* 全是鸡也凑不出这么多腿，用除法判界避免溢出 */
        return -1;
    }

    int diff = legs - 2 * heads;      /* 兔比鸡多出来的腿数 */
    if (diff % 2 != 0) {              /* 必须为偶数才有整数解 */
        return -1;
    }

    int r = diff / 2;                 /* 兔的只数 */
    int c = heads - r;                /* 鸡的只数 */
    if (c < 0) {
        return -1;
    }

    *chicken = c;
    *rabbit  = r;
    return 0;
}

/* 从一行文本中解析最多 max 个十进制整数，多余字符视为非法
 * 返回 n >= 0 : 成功解析到 n 个数（0 表示这一行没有数字）
 * 返回     -1 : 行内出现非数字字符或数值越界
 */
static int parse_ints(const char *line, int *out, int max)
{
    const char *p = line;
    int n = 0;

    if (line == NULL || out == NULL || max <= 0) {
        return -1;
    }

    for (;;) {
        char *end = NULL;
        long  v;

        while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
            ++p;
        }
        if (*p == '\0') {
            break;                    /* 行尾，正常结束 */
        }
        if (n >= max) {
            return -1;                /* 数字比预期多，整行判为非法 */
        }

        errno = 0;
        v = strtol(p, &end, 10);
        if (end == p || errno == ERANGE || v < INT_MIN || v > INT_MAX) {
            return -1;                /* 不是数字，或超出 int 表示范围 */
        }
        out[n++] = (int)v;
        p = end;
    }

    return n;
}

/* 读取一整行：返回 1 成功，返回 0 表示输入结束（EOF） */
static int read_line(char *buf, size_t size)
{
    if (buf == NULL || size == 0u) {
        return 0;
    }
    if (fgets(buf, (int)size, stdin) == NULL) {
        return 0;                     /* Ctrl+Z / Ctrl+D 或管道结束 */
    }
    return 1;
}

int main(void)
{
    char line[LINE_MAX_LEN];
    int  vals[2] = {0, 0};

    printf("===== 鸡兔同笼求解器 =====\n");
    printf("可每行输一个数（先头数、后腿数），也可一行写两个数，如 35 94\n");
    printf("输入非法会提示重输；Ctrl+Z（Windows）/ Ctrl+D（Linux）结束\n\n");

    for (;;) {
        int heads = 0, legs = 0, got = 0;

        /* ---------------- 头数 ---------------- */
        for (;;) {
            printf("请输入总头数: ");
            fflush(stdout);
            if (!read_line(line, sizeof(line))) {
                printf("\n输入结束，程序退出。\n");
                return 0;
            }
            got = parse_ints(line, vals, 2);
            if (got <= 0) {
                printf("不是合法整数，请重新输入。\n\n");
                continue;
            }
            heads = vals[0];
            break;
        }

        /* -------- 腿数：若同一行已给出第二个数，直接采用 -------- */
        if (got == 2) {
            legs = vals[1];
            printf("请输入总腿数: %d   （与头数同行输入，已读取）\n", legs);
        } else {
            for (;;) {
                printf("请输入总腿数: ");
                fflush(stdout);
                if (!read_line(line, sizeof(line))) {
                    printf("\n输入结束，程序退出。\n");
                    return 0;
                }
                got = parse_ints(line, vals, 1);
                if (got <= 0) {
                    printf("不是合法整数，请重新输入。\n\n");
                    continue;
                }
                legs = vals[0];
                break;
            }
        }

        if (heads < 0 || legs < 0) {
            printf("头数和腿数都不能为负数，请重新输入。\n\n");
            continue;
        }

        int chicken = 0, rabbit = 0;
        if (solve(heads, legs, &chicken, &rabbit) == 0) {
            printf("结果：鸡 %d 只，兔 %d 只。\n", chicken, rabbit);
            printf("校验：头数 %d + %d = %d，腿数 2*%d + 4*%d = %d\n\n",
                   chicken, rabbit, chicken + rabbit,
                   chicken, rabbit, 2 * chicken + 4 * rabbit);
        } else {
            printf("结果：无解！\n");
            printf("原因：腿数必须为偶数，且满足 2*头数 <= 腿数 <= 4*头数。\n\n");
        }
    }

    return 0;
}
