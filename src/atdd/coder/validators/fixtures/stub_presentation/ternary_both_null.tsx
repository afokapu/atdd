// Fixture for PRESENTATION-NOSTUB-005 — both ternary branches resolve to null.
export const TernaryBothNull = ({ flag }: { flag: boolean }) =>
  flag ? null : null;
