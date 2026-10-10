# -*- coding: utf-8 -*-
"""
鸡兔同笼求解程序
----------------
已知笼中鸡和兔的总头数 heads 和总腿数 legs，
求鸡(chicken)和兔(rabbit)各多少只。

建模：
    鸡 + 兔 = heads          (1)
    2*鸡 + 4*兔 = legs       (2)
由 (1)(2) 解得：
    兔 = (legs - 2*heads) / 2
    鸡 = heads - 兔
约束：heads、legs 均为非负整数，解必须落在 [0, heads] 内。
"""

from __future__ import annotations


def solve(heads: int, legs: int):
    """返回 (鸡数量, 兔数量)；若无合法解返回 None。

    使用公式法 O(1) 求解，并做严格合法性检查。
    """
    if not isinstance(heads, int) or not isinstance(legs, int):
        raise TypeError("heads 和 legs 必须是整数")
    if heads < 0 or legs < 0:
        return None

    # legs - 2*heads 必须为非负偶数，才能整除得到兔的数量
    remainder = legs - 2 * heads
    if remainder < 0 or remainder % 2 != 0:
        return None

    rabbits = remainder // 2
    chickens = heads - rabbits

    # 兔和鸡的数量都必须非负
    if rabbits < 0 or chickens < 0:
        return None
    return chickens, rabbits


def format_result(heads: int, legs: int) -> str:
    """把给定头数和腿数的求解结果格式化成一句话。"""
    ans = solve(heads, legs)
    if ans is None:
        return f"头数={heads}, 腿数={legs}: 无解"
    chickens, rabbits = ans
    return f"头数={heads}, 腿数={legs}: 鸡 {chickens} 只, 兔 {rabbits} 只"


def self_test() -> bool:
    """内置测试用例，返回是否全部通过。"""
    cases = [
        # (heads, legs, expected)  expected 为 None 表示无解
        (35, 94, (23, 12)),   # 经典题目：35 头 94 腿
        (8, 26, (3, 5)),
        (1, 4, (0, 1)),       # 全是兔
        (5, 10, (5, 0)),      # 全是鸡
        (0, 0, (0, 0)),       # 空笼
        (10, 15, None),       # 腿数为奇数，无解
        (10, 5, None),        # 腿太少，无解
        (10, 100, None),      # 腿太多，无解
    ]
    ok = True
    for heads, legs, expected in cases:
        got = solve(heads, legs)
        status = "OK " if got == expected else "FAIL"
        if got != expected:
            ok = False
        print(f"[{status}] 头={heads}, 腿={legs} -> {got} (期望 {expected})")
    return ok


def interactive() -> None:
    """交互式输入模式。"""
    print("鸡兔同笼求解器（输入非整数或负数将提示重试，直接回车退出）")
    while True:
        raw = input("请输入总头数和总腿数（用空格分隔）: ").strip()
        if not raw:
            print("已退出。")
            return
        parts = raw.split()
        if len(parts) != 2:
            print("请输入两个数字，例如: 35 94")
            continue
        try:
            heads, legs = int(parts[0]), int(parts[1])
        except ValueError:
            print("请输入整数。")
            continue
        print("  ->", format_result(heads, legs))


def main() -> None:
    import sys

    # 命令行直接传参: python chicken_rabbit.py 35 94
    if len(sys.argv) == 3:
        try:
            heads, legs = int(sys.argv[1]), int(sys.argv[2])
        except ValueError:
            print("参数必须是整数，例如: python chicken_rabbit.py 35 94")
            return
        print(format_result(heads, legs))
        return

    print("=== 自测 ===")
    all_ok = self_test()
    print("自测结果:", "全部通过" if all_ok else "存在失败用例")
    print()
    interactive()


if __name__ == "__main__":
    main()
