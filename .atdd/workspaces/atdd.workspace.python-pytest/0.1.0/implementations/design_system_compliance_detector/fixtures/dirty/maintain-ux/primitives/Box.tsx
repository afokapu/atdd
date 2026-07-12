import { h } from 'preact';
import { Card } from '../components/Card';

// DIRTY: a primitive reaches UP into the components layer (hierarchy break) and
// embeds a raw pixel literal without composing foundations (foundations break).
export function Box({ children }: { children: unknown }) {
  const style = { padding: '24px' };
  return (
    <div style={style}>
      <Card title="x" />
      {children}
    </div>
  );
}
