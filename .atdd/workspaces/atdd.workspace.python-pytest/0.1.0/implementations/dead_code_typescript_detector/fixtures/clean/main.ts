// GREEN fixture root: main.ts is an app entry point (graph root by convention).
// Imports app -> app.ts is reachable -> RAW = [] -> strict disposition PASS.
import { run } from './app';

run();
