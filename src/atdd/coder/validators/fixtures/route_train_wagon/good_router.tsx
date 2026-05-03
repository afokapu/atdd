// Fixture: a router file whose <TrainView trainId="..." /> resolves to a
// registered train (`registered-train-x`) whose wagons are all registered
// (`registered-wagon-y`). Used by:
//   - test_resolved_chain_passes (no violations)
//   - test_unregistered_wagon_in_train_fails (re-loaded trains.yaml has the
//     same trainId pointing at an unregistered wagon)
import { TrainView } from "../../runtime/TrainView";

export const Router = () => (
  <TrainView trainId="registered-train-x" />
);
