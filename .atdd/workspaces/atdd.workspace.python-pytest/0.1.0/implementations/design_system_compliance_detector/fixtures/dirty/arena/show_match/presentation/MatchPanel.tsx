import { h } from 'preact';
import { Box } from '@/maintain-ux/primitives';
import { Card } from '@/maintain-ux/components';

// Clean presentation component: composes design-system primitives + components,
// so it is NOT a -primitives / -orphan-ui violation, and it consumes Box + Card
// so those exports are not orphaned (only Orphan is).
export function MatchPanel({ title }: { title: string }) {
  return (
    <Box>
      <Card title={title} />
    </Box>
  );
}
