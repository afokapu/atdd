// Clean module — every function stays under all three complexity thresholds.

export function add(a: number, b: number): number {
  return a + b;
}

export function greet(name: string): string {
  if (name) {
    return `hello ${name}`;
  }
  return "hello";
}
