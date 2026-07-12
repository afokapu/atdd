import { FORECAST_SOURCE } from "../domain/forecast";

export function createForecastGateway() {
  return { source: FORECAST_SOURCE };
}
