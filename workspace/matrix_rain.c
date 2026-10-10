/*
 * matrix_rain.c —— 终端“矩阵雨”随机字符流模拟
 *
 * 功能：
 *   在控制台随机生成下落字符流，模拟《黑客帝国》数字雨效果。
 *   纯标准 C（C99），不依赖第三方库，Windows / Linux 均可编译。
 *
 * 编译：
 *   gcc -O2 -std=c99 -o matrix_rain matrix_rain.c
 * 运行：
 *   ./matrix_rain            # 默认 60 帧
 *   ./matrix_rain 120        # 指定帧数
 */

#define _POSIX_C_SOURCE 200809L     /* 让 nanosleep 在 -std=c99 下可见 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* 清屏与延时按平台封装：优先用 ANSI 转义，避免每帧创建 cmd.exe / clear 进程 */
#ifdef _WIN32
#include <windows.h>
#ifndef ENABLE_VIRTUAL_TERMINAL_PROCESSING
#define ENABLE_VIRTUAL_TERMINAL_PROCESSING 0x0004
#endif

static int have_vt = 0;             /* 控制台是否支持 ANSI 转义序列 */

static void setup_console(void)
{
    DWORD  mode = 0;
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);

    SetConsoleOutputCP(65001);      /* 输出代码页 -> UTF-8 */
    if (h != INVALID_HANDLE_VALUE && GetConsoleMode(h, &mode) &&
        SetConsoleMode(h, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING)) {
        have_vt = 1;
    }
}

static void sleep_ms(int ms)
{
    if (ms > 0) {
        Sleep((DWORD)ms);
    }
}

static void clear_screen(void)
{
    if (have_vt) {
        fputs("\033[H\033[2J", stdout);     /* 光标归位 + 清屏 */
    } else {
        system("cls");                      /* 老系统回退方案 */
    }
}
#else
#include <unistd.h>
#include <time.h>

static int have_vt = 1;

static void setup_console(void)
{
}

static void sleep_ms(int ms)
{
    struct timespec ts;

    if (ms <= 0) {
        return;
    }
    ts.tv_sec  = ms / 1000;
    ts.tv_nsec = (long)(ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

static void clear_screen(void)
{
    fputs("\033[H\033[2J", stdout);
}
#endif

#define WIDTH      60   /* 屏幕宽度（列数） */
#define HEIGHT     20   /* 屏幕高度（行数） */
#define MAX_DROPS  60   /* 最大雨滴数量 */

/* 雨滴：记录所在列、当前行、下落速度、拖尾长度 */
typedef struct {
    int col;        /* 列坐标 */
    int row;        /* 当前行坐标 */
    int speed;      /* 每帧下落行数 */
    int tail;       /* 拖尾长度 */
    int active;     /* 是否活跃 */
} Drop;

/* 随机整数 [lo, hi]，调用方保证 lo <= hi */
static int rand_range(int lo, int hi)
{
    if (hi <= lo) {
        return lo;
    }
    return lo + rand() % (hi - lo + 1);
}

/* 随机可见 ASCII 字符 */
static char rand_char(void)
{
    return (char)rand_range(33, 126);
}

/* 初始化雨滴数组 */
static void init_drops(Drop *drops, int n)
{
    for (int i = 0; i < n; ++i) {
        drops[i].col    = rand_range(0, WIDTH - 1);
        drops[i].row    = rand_range(-HEIGHT, 0);
        drops[i].speed  = rand_range(1, 2);
        drops[i].tail   = rand_range(3, 8);
        drops[i].active = 1;
    }
}

/* 渲染一帧 */
static void render(const Drop *drops, int n, int frame)
{
    /* 屏幕缓冲：每行 WIDTH 个字符 + 结束符 */
    char screen[HEIGHT][WIDTH + 1];

    /* 背景填充空格 */
    for (int r = 0; r < HEIGHT; ++r) {
        memset(screen[r], ' ', WIDTH);
        screen[r][WIDTH] = '\0';
    }

    /* 绘制所有雨滴的拖尾 */
    for (int i = 0; i < n; ++i) {
        if (!drops[i].active) continue;
        for (int t = 0; t < drops[i].tail; ++t) {
            int r = drops[i].row - t;
            if (r >= 0 && r < HEIGHT) {
                /* 头部用 '#'，拖尾用随机字符，形成渐隐感 */
                screen[r][drops[i].col] = (t == 0) ? '#' : rand_char();
            }
        }
    }

    clear_screen();
    printf("=== MATRIX RAIN  frame %d ===\n", frame);
    for (int r = 0; r < HEIGHT; ++r) {
        printf("%s\n", screen[r]);
    }
    fflush(stdout);
}

/* 推进一帧物理状态 */
static void update(Drop *drops, int n)
{
    for (int i = 0; i < n; ++i) {
        if (!drops[i].active) continue;
        drops[i].row += drops[i].speed;

        /* 完全离开屏幕后随机重生 */
        if (drops[i].row - drops[i].tail > HEIGHT) {
            drops[i].col   = rand_range(0, WIDTH - 1);
            drops[i].row   = rand_range(-HEIGHT / 2, 0);
            drops[i].speed = rand_range(1, 2);
            drops[i].tail  = rand_range(3, 8);
        }
    }
}

int main(int argc, char *argv[])
{
    int frames = 60;                 /* 默认帧数 */
    if (argc > 1) {
        int v = atoi(argv[1]);
        if (v > 0) frames = v;
    }

    setup_console();                 /* Windows：UTF-8 + 虚拟终端，ANSI 清屏才有效 */
    srand((unsigned)time(NULL));

    Drop drops[MAX_DROPS];
    init_drops(drops, MAX_DROPS);

    for (int f = 0; f < frames; ++f) {
        render(drops, MAX_DROPS, f);
        update(drops, MAX_DROPS);
        sleep_ms(80);                /* 帧间隔，Windows / Linux 统一入口 */
    }

    printf("\nDone. %d frames rendered.\n", frames);
    return 0;
}
