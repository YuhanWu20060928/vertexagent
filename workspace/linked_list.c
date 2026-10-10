/* ============================================================================
 * linked_list.c -- C 语言单链表完整实现（带头结点）
 * ----------------------------------------------------------------------------
 * 功能：尾插 / 头插 / 按值查找 / 按值删除 / 按位置插入 / 反转 / 求长度 /
 *       求中间结点 / 遍历打印 / 销毁
 * 编译：gcc -std=c11 -Wall -Wextra -O2 -o linked_list linked_list.c
 * 运行：./linked_list
 * ==========================================================================*/

#if defined(__MINGW32__) && !defined(__USE_MINGW_ANSI_STDIO)
#define __USE_MINGW_ANSI_STDIO 1    /* MinGW：改用符合 ISO C 格式的 printf */
#endif

#include <stdio.h>
#include <stdlib.h>
#include <inttypes.h>               /* PRIuMAX：跨平台输出 size_t */

/* ----------------------------- 数据结构定义 ----------------------------- */
typedef int ElemType;               /* 数据域类型，便于替换 */

typedef struct Node {
    ElemType      data;             /* 数据域 */
    struct Node  *next;             /* 指针域 */
} Node;

typedef struct {
    Node   *head;                   /* 头结点（不存有效数据） */
    size_t  size;                   /* 有效结点个数，O(1) 取长度 */
} List;

/* ----------------------------- 接口声明 ----------------------------- */
int     list_init(List *list);
int     list_push_back(List *list, ElemType value);
int     list_push_front(List *list, ElemType value);
int     list_insert(List *list, size_t pos, ElemType value);
int     list_remove(List *list, ElemType value);
long    list_find(const List *list, ElemType value);
int     list_reverse(List *list);
size_t  list_size(const List *list);
Node   *list_middle(const List *list);
void    list_print(const List *list);
void    list_destroy(List *list);

/* ----------------------------- 基本操作实现 ----------------------------- */

/* 创建空表：成功返回 1，失败返回 0 */
int list_init(List *list)
{
    if (list == NULL) {
        return 0;
    }
    list->head = (Node *)malloc(sizeof(Node));
    if (list->head == NULL) {
        return 0;                   /* 内存不足 */
    }
    list->head->next = NULL;
    list->size = 0;
    return 1;
}

/* 尾插：在链表尾部插入元素，成功返回 1 */
int list_push_back(List *list, ElemType value)
{
    Node *cur, *node;

    if (list == NULL) {
        return 0;
    }
    node = (Node *)malloc(sizeof(Node));
    if (node == NULL) {
        return 0;
    }
    node->data = value;
    node->next = NULL;

    cur = list->head;
    while (cur->next != NULL) {     /* 定位到最后一个结点 */
        cur = cur->next;
    }
    cur->next = node;
    list->size++;
    return 1;
}

/* 头插：在链表首部插入元素，成功返回 1，O(1) */
int list_push_front(List *list, ElemType value)
{
    Node *node;

    if (list == NULL) {
        return 0;
    }
    node = (Node *)malloc(sizeof(Node));
    if (node == NULL) {
        return 0;
    }
    node->data = value;
    node->next = list->head->next;
    list->head->next = node;
    list->size++;
    return 1;
}

/* 按位置插入：pos 从 0 开始计数，成功返回 1，越界返回 0 */
int list_insert(List *list, size_t pos, ElemType value)
{
    Node *cur, *node;
    size_t i;

    if (list == NULL || pos > list->size) {
        return 0;
    }
    node = (Node *)malloc(sizeof(Node));
    if (node == NULL) {
        return 0;
    }
    cur = list->head;
    for (i = 0; i < pos; i++) {     /* 移动到 pos 的前驱 */
        cur = cur->next;
    }
    node->data = value;
    node->next = cur->next;
    cur->next = node;
    list->size++;
    return 1;
}

/* 按值删除：删除第一个值为 value 的结点，成功返回 1，未找到返回 0 */
int list_remove(List *list, ElemType value)
{
    Node *prev, *cur;

    if (list == NULL || list->head->next == NULL) {
        return 0;
    }
    prev = list->head;
    cur  = list->head->next;
    while (cur != NULL && cur->data != value) {
        prev = cur;
        cur  = cur->next;
    }
    if (cur == NULL) {
        return 0;                   /* 未找到 */
    }
    prev->next = cur->next;
    free(cur);
    list->size--;
    return 1;
}

/* 按值查找：返回第一个匹配结点的下标，未找到返回 -1 */
long list_find(const List *list, ElemType value)
{
    const Node *cur;
    long index = 0;

    if (list == NULL) {
        return -1;
    }
    for (cur = list->head->next; cur != NULL; cur = cur->next, index++) {
        if (cur->data == value) {
            return index;
        }
    }
    return -1;
}

/* 反转链表：迭代法，O(n) 时间、O(1) 空间，成功返回 1 */
int list_reverse(List *list)
{
    Node *prev, *cur, *next;

    if (list == NULL) {
        return 0;
    }
    prev = NULL;
    cur  = list->head->next;
    while (cur != NULL) {
        next       = cur->next;     /* 先保存后继，防止断链 */
        cur->next  = prev;
        prev       = cur;
        cur        = next;
    }
    list->head->next = prev;
    return 1;
}

/* 求长度，O(1) */
size_t list_size(const List *list)
{
    return (list == NULL) ? 0u : list->size;
}

/* 求中间结点：快慢指针，偶数个结点返回中间偏左的那个，空表返回 NULL */
Node *list_middle(const List *list)
{
    Node *slow, *fast;

    if (list == NULL || list->head->next == NULL) {
        return NULL;
    }
    slow = list->head->next;
    fast = list->head->next;
    while (fast->next != NULL && fast->next->next != NULL) {
        slow = slow->next;
        fast = fast->next->next;
    }
    return slow;
}

/* 遍历打印 */
void list_print(const List *list)
{
    const Node *cur;
    int first = 1;

    if (list == NULL) {
        printf("(null list)\n");
        return;
    }
    printf("[");
    for (cur = list->head->next; cur != NULL; cur = cur->next) {
        printf("%s%d", first ? "" : " -> ", cur->data);
        first = 0;
    }
    printf("]  size = %" PRIuMAX "\n", (uintmax_t)list->size);
}

/* 销毁整表，释放全部内存 */
void list_destroy(List *list)
{
    Node *cur, *next;

    if (list == NULL || list->head == NULL) {
        return;
    }
    cur = list->head;
    while (cur != NULL) {
        next = cur->next;
        free(cur);
        cur = next;
    }
    list->head = NULL;
    list->size = 0;
}

/* --------------------------------- 测试 --------------------------------- */
int main(void)
{
    List list;
    Node *mid;
    long pos;
    size_t i;

    if (!list_init(&list)) {
        fprintf(stderr, "list_init failed\n");
        return EXIT_FAILURE;
    }

    printf("1) 尾插 1..5 : ");
    for (i = 1; i <= 5; i++) {
        list_push_back(&list, (ElemType)i);
    }
    list_print(&list);

    printf("2) 头插 0     : ");
    list_push_front(&list, 0);
    list_print(&list);

    printf("3) 位置 3 插入 99 : ");
    if (!list_insert(&list, 3, 99)) {       /* 越界或内存不足时才返回 0 */
        printf("插入失败（位置越界或内存不足）\n");
    }
    list_print(&list);

    pos = list_find(&list, 99);
    printf("4) 查找 99  -> 下标 %ld\n", pos);

    printf("5) 删除 99    : ");
    if (!list_remove(&list, 99)) {
        printf("未找到 99\n");
    }
    list_print(&list);

    printf("6) 删除不存在的 42 : %s\n",
           list_remove(&list, 42) ? "成功" : "未找到");

    mid = list_middle(&list);
    printf("7) 中间结点   -> %d\n", mid ? mid->data : -1);

    printf("8) 反转       : ");
    list_reverse(&list);
    list_print(&list);

    printf("9) 清空测试   : ");
    list_destroy(&list);
    printf("已释放全部结点，size = %" PRIuMAX "\n", (uintmax_t)list_size(&list));

    return EXIT_SUCCESS;
}
