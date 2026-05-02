// Clean fixture — guarded null with a sibling JSX return path. Must PASS.
export function ConditionalNullOk({ loading }: { loading: boolean }) {
  if (loading) return null;
  return <span>ready</span>;
}
