/*
 * life.c —— 命令行 Conway 生命游戏
 *
 * 用法:  life [代数] [随机密度百分比]
 *        life            默认演化 10 代，随机密度 25%
 *        life 20 0       只跑 20 代，不含随机细胞
 *
 * 规则: 活细胞邻居为 2 或 3 时存活; 死细胞邻居恰为 3 时复活。
 * 边界采用环形拓扑(上下左右环绕)，避免边界效应。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <limits.h>

#define WIDTH   48
#define HEIGHT  24

/* 双缓冲: cur 为当前代, nxt 为下一代 */
static unsigned char cur[HEIGHT][WIDTH];
static unsigned char nxt[HEIGHT][WIDTH];

/* 环形取模，保证索引始终落在 [0, n) 内 */
static int wrap(int v, int n)
{
    v %= n;
    return (v < 0) ? (v + n) : v;
}

/* 在环形坐标上点亮一个细胞 */
static void put(int x, int y)
{
    cur[wrap(y, HEIGHT)][wrap(x, WIDTH)] = 1;
}

/* 滑翔机: 5 个细胞，每 4 代沿对角方向平移一格 */
static void glider(int x, int y)
{
    put(x + 1, y + 0);
    put(x + 2, y + 1);
    put(x + 0, y + 2);
    put(x + 1, y + 2);
    put(x + 2, y + 2);
}

/* 闪烁器: 周期 2 的振荡器 */
static void blinker(int x, int y)
{
    put(x, y);
    put(x + 1, y);
    put(x + 2, y);
}

/* 方块: 静物，永不改变 */
static void block(int x, int y)
{
    put(x, y);
    put(x + 1, y);
    put(x, y + 1);
    put(x + 1, y + 1);
}

/* 撒入随机细胞, density 单位百分比 */
static void sprinkle(int density)
{
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            if (rand() % 100 < density) {
                put(x, y);
            }
        }
    }
}

/* 演化一代: 统计 8 邻居，按规则决定下一代状态 */
static void step(void)
{
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            int n = 0;

            for (int dy = -1; dy <= 1; ++dy) {
                for (int dx = -1; dx <= 1; ++dx) {
                    if (dx == 0 && dy == 0) {
                        continue;
                    }
                    n += cur[wrap(y + dy, HEIGHT)][wrap(x + dx, WIDTH)];
                }
            }

            if (cur[y][x]) {
                nxt[y][x] = (unsigned char)(n == 2 || n == 3);
            } else {
                nxt[y][x] = (unsigned char)(n == 3);
            }
        }
    }

    memcpy(cur, nxt, sizeof(cur));
}

/* 打印当前局面, 同时返回活细胞总数 */
static int show(int gen)
{
    int alive = 0;

    printf("generation %d\n", gen);
    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            putchar(cur[y][x] ? '#' : '.');
            alive += cur[y][x] ? 1 : 0;
        }
        putchar('\n');
    }
    putchar('\n');

    return alive;
}

/* 解析十进制整数：成功返回 0，非法字符或越界返回 -1 */
static int parse_int(const char *text, int *value)
{
    char *end = NULL;
    long  v;

    if (text == NULL || value == NULL) {
        return -1;
    }
    errno = 0;
    v = strtol(text, &end, 10);
    if (end == text || *end != '\0' || errno == ERANGE ||
        v < INT_MIN || v > INT_MAX) {
        return -1;
    }
    *value = (int)v;
    return 0;
}

int main(int argc, char *argv[])
{
    int generations = 10;               /* 默认演化 10 代 */
    int density     = 25;               /* 默认随机密度 25% */

    if (argc > 3) {
        fprintf(stderr, "用法: %s [代数] [随机密度 0-100]\n", argv[0]);
        return 2;
    }
    if (argc > 1 && parse_int(argv[1], &generations) != 0) {
        fprintf(stderr, "代数必须是整数: %s\n", argv[1]);
        return 2;
    }
    if (argc > 2 && parse_int(argv[2], &density) != 0) {
        fprintf(stderr, "随机密度必须是整数: %s\n", argv[2]);
        return 2;
    }

    if (generations < 0) {
        generations = 0;
    }
    if (density < 0) {
        density = 0;
    }
    if (density > 100) {
        density = 100;
    }

    srand(20240521u);   /* 固定种子, 保证每次运行结果可复现 */

    /* 固定图案: 一个滑翔机、一个闪烁器、一个方块 */
    glider(2, 2);
    blinker(30, 4);
    block(14, 18);
    sprinkle(density);

    int alive = 0;
    for (int g = 0; g <= generations; ++g) {
        alive = show(g);
        if (g < generations) {
            step();
        }
    }

    printf("done: %d generations, %d live cells on %dx%d board\n",
           generations, alive, WIDTH, HEIGHT);

    return 0;
}
