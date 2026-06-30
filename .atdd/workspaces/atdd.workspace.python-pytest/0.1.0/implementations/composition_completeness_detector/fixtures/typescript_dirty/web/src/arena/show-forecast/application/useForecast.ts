import { createForecastGateway } from "../integration/ForecastGateway";

export type ForecastState = {
  source: string;
};

// VIOLATION (coder.refactor.composition-consumer / SPEC-CODER-COMP-0001):
// this application file is consumed by presentation ONLY via `import type`
// (ForecastView.tsx), which is not composition evidence — so it has zero valid
// value consumers and is flagged, exactly as the legacy TS oracle flags it.
export function useForecast(): ForecastState {
  return createForecastGateway();
}
