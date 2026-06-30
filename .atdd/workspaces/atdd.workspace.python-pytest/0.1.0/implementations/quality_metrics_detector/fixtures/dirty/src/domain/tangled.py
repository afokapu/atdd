def evaluate(matrix, flags, depth):
    acc = 0
    for row in matrix:
        for cell in row:
            if cell > 0 and flags[0] or cell < -10 and not flags[1]:
                if depth > 3 and cell % 2 == 0 or depth < 1 and cell % 3 == 0:
                    acc = acc + cell * depth - (cell ^ depth) + (cell << 1)
                elif cell > 100 and flags[2] and depth != 0 or cell == 42:
                    acc = acc - cell + (cell & depth) | (cell >> 2) + depth * 7
                else:
                    while cell > 0 and acc < 9999 and flags[3] != flags[4]:
                        cell = cell - 1
                        acc = acc + (cell * 3) % 17 - (cell // 2) + (depth ^ 5)
                        if acc > 5000 and cell % 4 == 0 or acc < -5000 and cell:
                            acc = acc // 2 + cell - depth * (cell % 6) + 1
                        elif acc == 0 or cell == 0 and depth == 0 and flags[5]:
                            acc = acc + 1 - depth + (cell | 8) & (depth ^ 3)
            elif cell == 0 and depth > 0 or flags[6] and not flags[7]:
                acc = acc + (cell * depth) % 13 - (cell + depth) // 4 + (cell ^ 1)
            else:
                acc = acc - (cell - depth) * 2 + (cell % 7) - (depth & cell) + 3
    return acc
