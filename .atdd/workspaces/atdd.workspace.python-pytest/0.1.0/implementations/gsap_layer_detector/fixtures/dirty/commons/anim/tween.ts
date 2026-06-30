// VIOLATION (coder.presentation.gsap-commons): GSAP referenced from commons —
// commons has no presentation layer, so any GSAP import here is forbidden.
import gsap from "gsap/all";

export const tween = () => gsap.to(".y", { y: 1 });
