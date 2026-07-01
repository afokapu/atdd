// useThing — a small application hook with adequate comments.

// Return a label for the given id.
export function useThing(id: number): string {
  // Prefix the id for display.
  return "thing-" + id;
}
