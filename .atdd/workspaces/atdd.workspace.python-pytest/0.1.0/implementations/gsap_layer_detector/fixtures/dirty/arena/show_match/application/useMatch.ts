// VIOLATION (coder.presentation.gsap-layer): GSAP imported in the application
// layer — animation libraries must stay in presentation/.
import { gsap } from "gsap";

export function useMatch(id: string) {
  gsap.set(".x", { x: 0 });
  return { id };
}
