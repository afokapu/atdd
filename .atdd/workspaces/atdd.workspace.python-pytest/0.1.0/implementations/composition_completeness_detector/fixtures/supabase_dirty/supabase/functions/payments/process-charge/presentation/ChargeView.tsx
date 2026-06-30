import { useCharge } from "../application/useCharge";

// Value-imports the application hook, so application is satisfied.
export function ChargeView() {
  const charge = useCharge();
  return charge.currency;
}
