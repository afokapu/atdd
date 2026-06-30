import { h } from 'preact';
import { Box } from '../primitives';

// Component imports a lower layer (primitives) only — hierarchy- and
// foundations-clean. Consumed by MatchPanel so it is not orphaned.
export function Card({ title }: { title: string }) {
  return (
    <Box>
      <span>{title}</span>
    </Box>
  );
}
