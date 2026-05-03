#!/usr/bin/env node
// URN: component:govern-lifecycle:enforce-train-has-rendered-content:mount-train-harness:typescript:integration
// Runtime: node
// Purpose: Headless mount of a single FrontendTrainRunner train; emits a JSON record
//          conforming to src/atdd/tester/schemas/train-render-harness-result.schema.json
//          on stdout. Invoked per train by the Python validator
//          src/atdd/tester/validators/test_train_renders_content.py.
//
// Usage:   node .atdd/harness/mount-train.mjs --train <train_id>
//
// Contract:
//   * Exactly one JSON record on stdout's LAST line.
//   * Exit 0 on success, non-zero with stderr message on harness failure.
//   * The validator parses only the final stdout line so logging on prior lines
//     is allowed.
//
// Stub-detection heuristic (DOM peer to #334's source-AST detector): the
// rendered container's outerHTML is matched against /aria-busy=["']?true|
// data-loading|class=["'][^"']*\b(skeleton|loader|placeholder)\b/i.

import { JSDOM } from "jsdom";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import process from "node:process";

const args = parseArgs(process.argv.slice(2));
const trainId = args.train;
if (!trainId) {
  emit({
    trainId: "",
    textLength: 0,
    matchedExpectations: [],
    stubDetected: false,
    error: "missing --train <id> argument",
  });
  process.exit(2);
}

const startedAt = Date.now();
try {
  const result = await mountTrain(trainId);
  emit({ ...result, durationMs: Date.now() - startedAt });
  process.exit(0);
} catch (err) {
  emit({
    trainId,
    textLength: 0,
    matchedExpectations: [],
    stubDetected: false,
    error: `${err && err.message ? err.message : String(err)}`,
    durationMs: Date.now() - startedAt,
  });
  process.exit(1);
}

// ---------------------------------------------------------------------------

async function mountTrain(id) {
  const dom = new JSDOM(`<!doctype html><html><body><div id="root"></div></body></html>`, {
    url: "http://localhost/",
    pretendToBeVisual: true,
  });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.HTMLElement = dom.window.HTMLElement;

  const repoRoot = process.cwd();
  const meta = await loadTrainMetadata(repoRoot, id);
  const expectations = (meta?.expected_content?.must_contain ?? []).filter(Boolean);

  const runner = await loadRunner(repoRoot);
  const view = await runner.runTrain(id);
  if (view == null) {
    return {
      trainId: id,
      textLength: 0,
      matchedExpectations: [],
      stubDetected: false,
    };
  }

  // The runner is expected to mount into #root (FrontendTrainRunner contract).
  // If it returned a node/string, attach it directly.
  const root = dom.window.document.getElementById("root");
  if (typeof view === "string") {
    root.innerHTML = view;
  } else if (view && typeof view === "object" && "outerHTML" in view) {
    root.appendChild(view);
  }

  const html = root.outerHTML || "";
  const text = (root.textContent || "").trim();

  const matched = expectations.filter((needle) => html.includes(needle) || text.includes(needle));
  const stub = detectStub(html);

  return {
    trainId: id,
    textLength: text.length,
    matchedExpectations: matched,
    stubDetected: stub.detected,
    stubReason: stub.reason,
  };
}

async function loadTrainMetadata(repoRoot, id) {
  const path = resolve(repoRoot, "plan", "_trains", `${id}.yaml`);
  try {
    const yaml = await readFile(path, "utf8");
    return parseYamlShallow(yaml);
  } catch {
    return null;
  }
}

async function loadRunner(repoRoot) {
  const candidates = [
    "web/src/composition/frontend-train-runner.ts",
    "web/src/composition/FrontendTrainRunner.ts",
    "web/src/wagons/composition/frontend-train-runner.ts",
  ];
  for (const rel of candidates) {
    try {
      const mod = await import(resolve(repoRoot, rel));
      const Runner = mod.FrontendTrainRunner ?? mod.default;
      if (Runner) return new Runner();
    } catch {
      /* try next candidate */
    }
  }
  throw new Error("FrontendTrainRunner not found in expected paths");
}

function detectStub(html) {
  if (!html) return { detected: false, reason: null };
  if (/aria-busy\s*=\s*["']?true/i.test(html)) {
    return { detected: true, reason: "aria-busy=true on rendered container" };
  }
  if (/data-loading\b/i.test(html)) {
    return { detected: true, reason: "data-loading marker present" };
  }
  const m = html.match(/class\s*=\s*["'][^"']*\b(skeleton|loader|placeholder)\b/i);
  if (m) {
    return { detected: true, reason: `class contains '${m[1]}'` };
  }
  return { detected: false, reason: null };
}

// Minimal YAML parser for the metadata schema (top-level keys + expected_content
// nested object with arrays of strings). Avoids a runtime dep on js-yaml.
function parseYamlShallow(text) {
  const out = {};
  let cur = out;
  const stack = [{ indent: -1, node: out, key: null }];
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, "").trimEnd();
    if (!line.trim()) continue;
    const indent = line.match(/^ */)[0].length;
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    cur = stack[stack.length - 1].node;
    const trimmed = line.trim();
    if (trimmed.startsWith("- ")) {
      const last = stack[stack.length - 1];
      const arr = Array.isArray(last.node[last.key]) ? last.node[last.key] : (last.node[last.key] = []);
      arr.push(stripQuotes(trimmed.slice(2).trim()));
      continue;
    }
    const m = trimmed.match(/^([A-Za-z_][\w-]*)\s*:\s*(.*)$/);
    if (!m) continue;
    const key = m[1];
    const val = m[2];
    if (val === "") {
      cur[key] = {};
      stack.push({ indent, node: cur[key], key });
    } else {
      cur[key] = stripQuotes(val);
    }
  }
  return out;
}

function stripQuotes(s) {
  if ((s.startsWith('"') && s.endsWith('"')) || (s.startsWith("'") && s.endsWith("'"))) {
    return s.slice(1, -1);
  }
  return s;
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (a.startsWith("--")) {
      const k = a.slice(2);
      const v = argv[i + 1];
      if (v && !v.startsWith("--")) {
        out[k] = v;
        i += 1;
      } else {
        out[k] = true;
      }
    }
  }
  return out;
}

function emit(record) {
  process.stdout.write(JSON.stringify(record) + "\n");
}
