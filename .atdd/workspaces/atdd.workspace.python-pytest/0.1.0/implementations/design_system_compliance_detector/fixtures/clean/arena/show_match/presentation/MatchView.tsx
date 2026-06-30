import { h } from 'preact';
import { Box } from '@/maintain-ux/primitives';
import { Card } from '@/maintain-ux/components';

// Presentation component composes design-system primitives + components (so the
// -primitives and -orphan-ui rules pass), uses no raw colors and no hardcoded
// spacing (so -token-color and -token-hardcoded pass). Box + Card are imported
// here, so neither design-system export is orphaned.
export function MatchView({ title }: { title: string }) {
  return (
    <Box>
      <Card title={title} />
    </Box>
  );
}
