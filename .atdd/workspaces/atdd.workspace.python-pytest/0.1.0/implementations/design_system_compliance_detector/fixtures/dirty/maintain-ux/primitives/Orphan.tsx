import { h } from 'preact';
import { spacing } from '../foundations';

// DIRTY: this primitive is exported from the index but no consumer imports it
// (orphan-export). It is otherwise hierarchy- and foundations-clean, so it
// triggers ONLY the orphan-export rule.
export function Orphan({ label }: { label: string }) {
  return <em style={{ padding: spacing.sm }}>{label}</em>;
}
