// URN: component:govern-lifecycle:enforce-train-has-rendered-content:harness-vitest-config:typescript:integration
// Runtime: node
// Purpose: Vitest config used by the train-render harness when consumer repos run
//          mount-train.mjs through `vitest run` instead of standalone node. Standalone
//          node + jsdom is the default invocation (see mount-train.mjs); this config
//          is provided so a consumer repo can opt into a vitest-driven harness suite
//          if it already has @testing-library/preact configured.

import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: [".atdd/harness/mount-train.mjs"],
    environment: "jsdom",
    testTimeout: 30000,
    pool: "forks",
    reporters: ["default"],
    coverage: { enabled: false },
  },
});
