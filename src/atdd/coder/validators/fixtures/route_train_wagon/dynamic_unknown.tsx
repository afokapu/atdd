// Fixture: a router file whose trainId binds to a prop pass-through, i.e.
// not a static literal and not resolvable from a same-file const. Drives
// BOUNDARIES-ROUTE-COVERAGE-003 (severity 1, advisory warning).
import { TrainView } from "../../runtime/TrainView";

interface RouterProps {
  trainId: string;
}

export const Router = (props: RouterProps) => (
  <TrainView trainId={props.trainId} />
);
