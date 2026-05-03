// Fixture: a router file referencing a trainId that is NOT in plan/_trains.yaml.
// Drives BOUNDARIES-ROUTE-COVERAGE-001 (severity 3, hard fail).
import { TrainView } from "../../runtime/TrainView";

export const Router = () => (
  <TrainView trainId="does-not-exist" />
);
