// Greeting — a tiny, well-formed presentation component.
import React from "react";

// Props for the greeting card.
interface Props {
  name: string;
}

export function Greeting({ name }: Props) {
  // Render a friendly hello.
  return <span>Hello {name}</span>;
}
