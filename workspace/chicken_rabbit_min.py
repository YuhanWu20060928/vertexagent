def solve(heads, legs):
    r = (legs - 2 * heads) / 2
    if r < 0 or r != int(r) or heads - r < 0:
        return None
    return int(heads - r), int(r)


if __name__ == "__main__":
    heads, legs = 35, 94
    print(solve(heads, legs))
