/*
 * confession.c —— 一封会跳动的情书
 *
 * 用法:  confession [--fast] [--plain] [--delay=毫秒]
 *        --fast     关掉打字机延迟，瞬间输出全篇
 *        --plain    关闭 ANSI 彩色（重定向到文件或旧终端时使用）
 *        --delay=n  自定义逐字延迟，默认 18ms
 *
 * 流程: 打字机独白 -> 心形字符画 -> 心跳动画 -> 情诗 -> 求一个答案。
 * 心形由解析式 (x^2 + y^2 - 1)^3 - x^2 * y^3 <= 0 生成，
 * 并按到边界距离做墨色渐变，缩放系数让心脏一张一缩。
 */

#define _POSIX_C_SOURCE 200809L     /* 让 nanosleep 在 -std=c11 下可见 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

/* 毫秒级休眠：Linux 用 nanosleep（usleep 单次不能超过 1e6 us） */
#ifdef _WIN32
#include <windows.h>
#ifndef ENABLE_VIRTUAL_TERMINAL_PROCESSING
#define ENABLE_VIRTUAL_TERMINAL_PROCESSING 0x0004
#endif

static void sleep_ms(int ms)
{
    if (ms > 0) {
        Sleep((DWORD)ms);
    }
}

/* Windows 控制台默认是 GBK 且不解析 ANSI 转义序列，
 * 中文会乱码、颜色会显示成 "\033[38;5;223m" 字面量，这里统一打开 UTF-8 与 VT 支持 */
static void setup_console(void)
{
    DWORD  mode = 0;
    HANDLE h = GetStdHandle(STD_OUTPUT_HANDLE);

    SetConsoleOutputCP(65001);      /* 输出代码页 -> UTF-8 */
    SetConsoleCP(65001);            /* 输入代码页 -> UTF-8 */
    if (h != INVALID_HANDLE_VALUE && GetConsoleMode(h, &mode)) {
        SetConsoleMode(h, mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING);
    }
}
#else
#include <unistd.h>
#include <time.h>

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

/* POSIX 终端原生支持 UTF-8 与 ANSI 转义，无需设置 */
static void setup_console(void)
{
}
#endif

#define HEART_W   57          /* 心形字符画宽度（列） */
#define HEART_H   27          /* 心形字符画高度（行） */
#define RAMP      " .:-=+*#%@" /* 墨色梯度：下标越大越浓 */
#define RAMP_LEN  10

/* 256 色中的粉色系，按行做上下渐变 */
static const int PINK[] = { 225, 218, 211, 205, 199, 163, 127, 163, 199, 205, 211, 218, 225 };
#define PINK_N ((int)(sizeof(PINK) / sizeof(PINK[0])))

static int use_color = 1;    /* 是否输出 ANSI 转义序列 */
static int delay_ms  = 18;   /* 打字机逐字延迟 */

/* 逐字吐出文本，模拟手写时的停顿 */
static void say(const char *text, int pause)
{
    if (use_color) {
        fputs("\033[38;5;223m", stdout);
    }
    for (const char *p = text; *p != '\0'; ++p) {
        putchar(*p);
        fflush(stdout);
        sleep_ms(delay_ms);
    }
    if (use_color) {
        fputs("\033[0m", stdout);
    }
    putchar('\n');
    sleep_ms(pause);
}

/* 打印缩放比例为 scale 的心形；scale > 1 即为“心跳” */
static void draw_heart(double scale)
{
    const double xmin = -1.50 * scale, xmax = 1.50 * scale;
    const double ymin = -1.35 * scale, ymax = 1.25 * scale;

    for (int row = 0; row < HEART_H; ++row) {
        if (use_color) {
            printf("\033[38;5;%dm", PINK[row % PINK_N]);
        }

        for (int col = 0; col < HEART_W; ++col) {
            double x  = xmin + (col + 0.5) * (xmax - xmin) / HEART_W;
            double y  = ymax - (row + 0.5) * (ymax - ymin) / HEART_H;
            double a  = x * x + y * y - 1.0;
            double f  = a * a * a - x * x * y * y * y;   /* < 0 表示在心形内部 */
            char   ch = ' ';

            if (f <= 0.0) {
                double depth = -f;
                double t     = depth / (depth + 1.2 * scale); /* 越靠边界越接近 0 */
                int    idx   = (int)((1.0 - t) * (RAMP_LEN - 1) + 0.5);

                if (idx < 0) {
                    idx = 0;
                }
                if (idx >= RAMP_LEN) {
                    idx = RAMP_LEN - 1;
                }
                ch = RAMP[idx];
            }
            putchar(ch);
        }

        if (use_color) {
            fputs("\033[0m", stdout);
        }
        putchar('\n');
    }
}

int main(int argc, char *argv[])
{
    setup_console();                /* Windows：切 UTF-8 代码页并开启 ANSI 转义解析 */

    for (int i = 1; i < argc; ++i) {
        if (strcmp(argv[i], "--plain") == 0) {
            use_color = 0;
        } else if (strcmp(argv[i], "--fast") == 0) {
            delay_ms = 0;
        } else if (strncmp(argv[i], "--delay=", 8) == 0) {
            delay_ms = atoi(argv[i] + 8);
            if (delay_ms < 0) {
                delay_ms = 0;
            }
        }
    }

    say("有些话在喉咙里排练了很久，今天终于敢写下来。", 260);
    say("它不长，但每一个字都朝着你的方向。", 420);
    putchar('\n');

    /* 一颗静止的心 */
    draw_heart(1.00);
    putchar('\n');

    /* 心跳：两次轻跳之后一次重跳，最后回到平静 */
    static const double BEAT[] = { 1.00, 1.08, 1.01, 1.13, 1.02, 1.00 };
    for (int i = 0; i < (int)(sizeof(BEAT) / sizeof(BEAT[0])); ++i) {
        draw_heart(BEAT[i]);
        putchar('\n');
        sleep_ms(delay_ms > 0 ? 130 : 0);
    }
    say("[ 刚才那阵声音，是我的心跳，不是风 ]", 420);
    putchar('\n');

    say("你出现的那天，我的心跳忽然有了正当的理由。", 300);
    say("世界很大，而我只想把余生的坐标交给你。", 300);
    say("风会替我转达，星星会替我作证。", 420);
    putchar('\n');

    say("所以 —— 你愿意让我的世界里，从此多一个你吗？", 300);

    char buf[128];
    for (;;) {
        if (use_color) {
            fputs("\033[38;5;205m", stdout);
        }
        printf("请回答 (y / n) : ");
        fflush(stdout);
        if (use_color) {
            fputs("\033[0m", stdout);
        }

        if (fgets(buf, sizeof(buf), stdin) == NULL) {
            /* 没有输入（管道结束）时不尴尬，温柔地记作点头 */
            putchar('\n');
            say("( 你没有说话，那我就当是你害羞地点了点头 ）", 300);
            strcpy(buf, "y");
            break;
        }
        if (buf[0] == '\n' || buf[0] == '\r') {     /* 直接回车也算点头 */
            strcpy(buf, "y");
            break;
        }
        if (buf[0] == 'y' || buf[0] == 'Y' || buf[0] == 'n' || buf[0] == 'N') {
            break;                                  /* 有效回答，跳出询问 */
        }
        printf("（它只听懂了 y 和 n，请再答一次）\n");
    }

    putchar('\n');
    if (buf[0] == 'n' || buf[0] == 'N') {
        say("没关系，喜欢从来不是打扰。", 300);
        say("这封信我先寄存在风里，等你哪天想拆开，我还在原来的地方。", 300);
    } else {
        say("谢谢你，从这一刻起，我的心跳不用再伪装成安静。", 300);
        say("以后每一个平凡的日子，我都想写上有你的落款。", 300);
        putchar('\n');
        draw_heart(0.55);
        say("—— 永远站在你身边的那个人", 200);
    }

    return 0;
}
