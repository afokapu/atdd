def process(values):
    a = values[0]
    b = values[1]
    c = a + b
    d = c * 2
    e = d - a
    f = e / 3
    g = f + b
    h = g % 5
    i = h * h
    j = i + c
    k = j - d
    result = [a, b, c, d, e]
    result.append(f)
    result.append(g)
    result.append(h)
    result.append(i)
    result.append(j)
    result.append(k)
    result.sort()
    return result
