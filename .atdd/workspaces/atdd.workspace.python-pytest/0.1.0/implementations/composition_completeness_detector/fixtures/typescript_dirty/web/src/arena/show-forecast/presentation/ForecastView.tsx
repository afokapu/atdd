import type { ForecastState } from "../application/useForecast";

type Props = {
  forecast: ForecastState;
};

export function ForecastView(props: Props) {
  return <section>{props.forecast.source}</section>;
}
