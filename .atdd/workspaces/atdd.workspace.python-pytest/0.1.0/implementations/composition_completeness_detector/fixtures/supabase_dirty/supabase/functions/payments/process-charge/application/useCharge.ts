import { CURRENCY } from "../domain/money";

// Consumes the domain (so domain is satisfied) but deliberately does NOT import
// the integration ChargeGateway — leaving that integration file unconsumed.
export function useCharge() {
  return { currency: CURRENCY, amount: 0 };
}
