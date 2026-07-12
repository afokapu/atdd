import { CURRENCY } from "../domain/money";

// VIOLATION (coder.refactor.composition-consumer / SPEC-CODER-COMP-0002):
// this integration file is never imported by the application layer (useCharge.ts
// imports only the domain), so it has zero valid consumers and is flagged —
// the same verdict the legacy supabase oracle produces.
export function createChargeGateway() {
  return { currency: CURRENCY };
}
