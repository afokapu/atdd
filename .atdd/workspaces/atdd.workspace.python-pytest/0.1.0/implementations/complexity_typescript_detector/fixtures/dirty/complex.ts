// Dirty module — each function trips exactly one complexity threshold.
//
//   classify  -> cyclomatic complexity > 10
//   deepNest  -> nesting depth > 4
//   longFn    -> function length (LOC) > 50

export function classify(value: number, mode: string, flag: boolean): number {
  let result = 0;
  if (value > 0 && mode === "a") {
    result = 1;
  } else if (value > 1 || flag) {
    result = 2;
  } else if (value > 2) {
    result = 3;
  }
  for (let i = 0; i < value; i++) {
    if (i % 2 === 0 && flag) {
      result += i;
    }
  }
  while (result < 100 || mode === "x") {
    result += 1;
  }
  switch (mode) {
    case "a":
      result += 1;
      break;
    case "b":
      result += 2;
      break;
  }
  return result;
}

export function deepNest(data: number[][][]): number {
  if (data) {
    for (const a of data) {
      if (a) {
        for (const b of a) {
          if (b) {
            return b.length;
          }
        }
      }
    }
  }
  return 0;
}

export function longFn(): number {
  let x0 = 0;
  let x1 = 1;
  let x2 = 2;
  let x3 = 3;
  let x4 = 4;
  let x5 = 5;
  let x6 = 6;
  let x7 = 7;
  let x8 = 8;
  let x9 = 9;
  let x10 = 10;
  let x11 = 11;
  let x12 = 12;
  let x13 = 13;
  let x14 = 14;
  let x15 = 15;
  let x16 = 16;
  let x17 = 17;
  let x18 = 18;
  let x19 = 19;
  let x20 = 20;
  let x21 = 21;
  let x22 = 22;
  let x23 = 23;
  let x24 = 24;
  let x25 = 25;
  let x26 = 26;
  let x27 = 27;
  let x28 = 28;
  let x29 = 29;
  let x30 = 30;
  let x31 = 31;
  let x32 = 32;
  let x33 = 33;
  let x34 = 34;
  let x35 = 35;
  let x36 = 36;
  let x37 = 37;
  let x38 = 38;
  let x39 = 39;
  let x40 = 40;
  let x41 = 41;
  let x42 = 42;
  let x43 = 43;
  let x44 = 44;
  let x45 = 45;
  let x46 = 46;
  let x47 = 47;
  let x48 = 48;
  return x0 + x48;
}
