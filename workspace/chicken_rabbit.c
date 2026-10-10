/* 鸡兔同笼：已知总头数 heads 和总腿数 legs，求鸡、兔各几只
 *   兔 = (legs - 2*heads) / 2 ；鸡 = heads - 兔
 *
 * 编译：gcc -std=c11 -Wall -Wextra -Wpedantic -O2 -o chicken_rabbit chicken_rabbit.c
 * 用法：chicken_rabbit [头数] [腿数]     不带参数时跑内置样例
 *
 * 说明：64 位输出统一用 <inttypes.h> 的 PRId64。MinGW 的 MSVCRT printf 不认
 *       %lld / %zu，打开 ANSI stdio 后该宏展开为标准的 lli，且能通过 -Wpedantic。
 */
#if defined(__MINGW32__) && !defined(__USE_MINGW_ANSI_STDIO)
#define __USE_MINGW_ANSI_STDIO 1     /* 让 MinGW 使用符合 ISO C 格式的 printf */
#endif

#include <stdio.h>
#include <stdlib.h>
#include <errno.h>
#include <inttypes.h>

static int solve(long long heads, long long legs, long long *chicken, long long *rabbit);
static int parse_ll(const char *text, long long *value);
static void report(long long heads, long long legs);

/* 成功返回 0 并写回 *chicken / *rabbit；无解返回 -1 */
static int solve(long long heads, long long legs, long long *chicken, long long *rabbit)
{
    if (chicken == NULL || rabbit == NULL || heads < 0 || legs < 0) {
        return -1;
    }

    /* 先用除法判界，避免 2*heads 溢出 */
    if (heads > legs / 2) {              /* 全是鸡也凑不出这么多腿 */
        return -1;
    }

    long long diff = legs - 2 * heads;   /* 兔多出的腿数，此时非负且不会溢出 */
    if (diff % 2 != 0) {                 /* 必须是偶数才有整数解 */
        return -1;
    }

    long long r = diff / 2;              /* 兔的只数 */
    long long c = heads - r;             /* 鸡的只数 */
    if (r < 0 || c < 0) {
        return -1;
    }

    *chicken = c;
    *rabbit  = r;
    return 0;
}

/* 严格解析十进制整数：成功返回 0，非法或越界返回 -1 */
static int parse_ll(const char *text, long long *value)
{
    char     *end = NULL;
    long long v;

    if (text == NULL || value == NULL) {
        return -1;
    }
    errno = 0;
    v = strtoll(text, &end, 10);
    if (end == text || *end != '\0' || errno == ERANGE) {
        return -1;
    }
    *value = v;
    return 0;
}

static void report(long long heads, long long legs)
{
    long long c = 0, r = 0;

    if (solve(heads, legs, &c, &r) == 0) {
        printf("头数=%" PRId64 ", 腿数=%" PRId64 ": 鸡 %" PRId64 " 只, 兔 %" PRId64 " 只\n",
               heads, legs, c, r);
    } else {
        printf("头数=%" PRId64 ", 腿数=%" PRId64 ": 无解\n", heads, legs);
    }
}

int main(int argc, char *argv[])
{
    if (argc == 3) {
        long long heads = 0, legs = 0;
        if (parse_ll(argv[1], &heads) != 0 || parse_ll(argv[2], &legs) != 0) {
            fprintf(stderr, "参数必须是整数: %s %s\n", argv[1], argv[2]);
            return 2;
        }
        report(heads, legs);
        return 0;
    }

    if (argc != 1) {
        fprintf(stderr, "用法: %s [总头数] [总腿数]\n", argv[0]);
        return 2;
    }

    /* 无参数时跑一组内置示例，覆盖有解、退化解与无解 */
    static const long long H[] = {35, 8, 5, 10, 10};
    static const long long L[] = {94, 26, 10, 15, 100};
    size_t n = sizeof(H) / sizeof(H[0]);

    for (size_t i = 0; i < n; ++i) {
        report(H[i], L[i]);
    }
    return 0;
}
