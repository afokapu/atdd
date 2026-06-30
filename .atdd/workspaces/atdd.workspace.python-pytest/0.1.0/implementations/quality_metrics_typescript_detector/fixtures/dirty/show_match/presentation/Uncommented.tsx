import React from "react";

export function Uncommented(props: { rows: number[][]; factor: number }) {
  const out: number[] = [];
  const factor = props.factor;
  for (const row of props.rows) {
    let sum = 0;
    for (const cell of row) {
      sum = sum + cell * factor;
      sum = sum - cell;
    }
    out.push(sum);
  }
  const doubled = out.map((value) => value * 2);
  const filtered = doubled.filter((value) => value > 0);
  const total = filtered.reduce((acc, value) => acc + value, 0);
  const label = "total-" + total;
  const payload = { total, label, count: filtered.length };
  return <pre>{JSON.stringify(payload)}</pre>;
}
