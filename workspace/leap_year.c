#include <stdio.h>

// 判断是否为闰年
int is_leap_year(int year) {
    // 能被 400 整除的是闰年
    if (year % 400 == 0) {
        return 1;
    }
    // 能被 100 整除但不是 400 的，不是闰年
    if (year % 100 == 0) {
        return 0;
    }
    // 能被 4 整除的是闰年
    if (year % 4 == 0) {
        return 1;
    }
    // 其他都不是闰年
    return 0;
}

int main() {
    int year;
    
    printf("请输入一个年份：");
    scanf("%d", &year);
    
    if (is_leap_year(year)) {
        printf("%d年是闰年\n", year);
    } else {
        printf("%d年不是闰年\n", year);
    }
    
    return 0;
}
