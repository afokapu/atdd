import { useCharge } from "./application/useCharge";

// Thin edge-function entry point (the supabase composition root). It wires the
// application hook, but `composition` is not a valid consumer layer for the
// supabase stack, so it does not satisfy the integration->application rule.
export default function handler() {
  return useCharge();
}
