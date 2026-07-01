import { h } from 'preact';
import { Box } from '../primitives';

// Component imports a lower layer (primitives) only — allowed by the hierarchy.
// No raw pixel literals, so the foundations rule passes too.
export function Card({ title }: { title: string }) {
  return (
    <Box>
      <span>{title}</span>
    </Box>
  );
}
