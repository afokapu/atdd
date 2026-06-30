// GREEN fixture: GSAP is imported ONLY from a presentation-layer file. The
// detector emits ZERO violations for this scan root.
import { gsap } from "gsap";
import { useEffect } from "react";

export function MatchAnimation() {
  useEffect(() => {
    gsap.to(".match", { opacity: 1 });
  }, []);
  return null;
}
