import { h } from 'preact';
import { spacing } from '../foundations';

// Primitive composes foundations tokens — no raw pixel literals, imports only
// from a lower layer (foundations), so the hierarchy + foundations rules pass.
export function Box({ children }: { children: unknown }) {
  const style = { padding: spacing.md, gap: spacing.sm };
  return <div style={style}>{children}</div>;
}
