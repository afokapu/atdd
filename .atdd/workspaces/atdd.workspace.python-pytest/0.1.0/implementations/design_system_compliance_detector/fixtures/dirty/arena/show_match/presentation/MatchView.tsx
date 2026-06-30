import { h } from 'preact';

// DIRTY: a presentation component that renders JSX but imports nothing from the
// design system (triggers BOTH -primitives and -orphan-ui), embeds a raw hex
// color literal (-token-color), and hardcodes a pixel spacing value
// (-token-hardcoded).
export function MatchView({ title }: { title: string }) {
  const accent = '#3a7bd5';
  const style = { padding: '16px', color: accent };
  return (
    <div style={style}>
      <span>{title}</span>
    </div>
  );
}
