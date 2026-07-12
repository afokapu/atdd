// Allowed: GSAP in the presentation layer is fine — produces NO violation even
// in the dirty fixture (proves the layer predicate, not a blanket gsap ban).
import { gsap } from "gsap";

export function MatchAnimation() {
  return gsap.timeline();
}
