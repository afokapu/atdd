// Clean fixture — passthrough container renders {children}. Must PASS.
import type { ComponentChildren } from "preact";

export function PassthroughChildrenOk({ children }: { children: ComponentChildren }) {
  return <div>{children}</div>;
}
