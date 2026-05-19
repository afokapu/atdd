# ATDD Adapter / Model Reference

This document is the canonical reference for the multi-LLM spawn surface
(`atdd spawn --llm <adapter-id>`). It covers every adapter registered in
`ADAPTER_REGISTRY` (see `src/atdd/coach/commands/spawn.py`), the environment
variables each adapter requires, the permission policy it applies, and the
recipe for registering a new adapter.

---

## Registered Adapters

| Adapter ID | LLM / Shell Binary | Required Env Var | Launch mechanism |
|---|---|---|---|
| `claude-code` | Claude Code CLI (`claude`) | `ANTHROPIC_API_KEY` | `claude --permission-mode acceptEdits` — prompt injected post-boot |
| `claude-glm` | Claude Code CLI → z.ai GLM-5.1 endpoint | `Z_AI_API_KEY` | `claude --model glm-5.1 --permission-mode acceptEdits` — prompt injected post-boot |
| `claude-gpt` | Claude Code CLI → OpenRouter GPT-5.5 | `OPENROUTER_API_KEY` | `claude --model gpt-5.5 --permission-mode acceptEdits` — prompt injected post-boot |
| `codex` | OpenAI Codex CLI (`codex`) | `OPENAI_API_KEY` | `codex exec --prompt-file <path>` |
| `gemini` | Google Gemini CLI (`gemini`) | `GOOGLE_API_KEY` | `gemini generate --prompt-file <path>` |

---

## Adapter Detail

### `claude-code`

**Binary:** `claude` (Claude Code CLI, installed separately)

**Environment Variables:**

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | API key for the Anthropic platform. Obtain from [console.anthropic.com](https://console.anthropic.com). |

**Permission Policy:**

```
--permission-mode acceptEdits
--allowedTools "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
```

This policy is the sanctioned alternative to the forbidden
`--dangerouslySkipPermissions` / `bypassPermissions` flags (see repo memory
rule and `CLAUDE.md`). It gives the spawned agent autonomous flow without
bypassing the permission system entirely.

**Launch Command:**

```sh
claude --permission-mode acceptEdits \
  --allowedTools "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
```

The launch prompt is injected post-boot via `backend.paste_text` + `send_key("Enter")`,
not as a positional argument (Claude Code v2.1.x ignores positional prompts in
interactive mode — see `_claude_code_adapter` docstring for details).

---

### `claude-glm`

**Binary:** `claude` (Claude Code CLI) routed to the z.ai GLM-5.1 endpoint via
`--model glm-5.1`.

**Environment Variables:**

| Variable | Required | Description |
|---|---|---|
| `Z_AI_API_KEY` | Yes | API key for the z.ai platform (GLM model endpoint). |

**Permission Policy:** Same as `claude-code` — `--permission-mode acceptEdits` with the
same `--allowedTools` allowlist.

**Launch Command:**

```sh
claude --model glm-5.1 --permission-mode acceptEdits \
  --allowedTools "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
```

---

### `claude-gpt`

**Binary:** `claude` (Claude Code CLI) routed to OpenRouter GPT-5.5 via
`--model gpt-5.5`.

**Environment Variables:**

| Variable | Required | Description |
|---|---|---|
| `OPENROUTER_API_KEY` | Yes | API key for the OpenRouter platform. |

**Permission Policy:** Same as `claude-code`.

**Launch Command:**

```sh
claude --model gpt-5.5 --permission-mode acceptEdits \
  --allowedTools "Bash Edit Write Read TodoWrite Glob Grep WebFetch"
```

---

### `codex`

**Binary:** `codex` (OpenAI Codex CLI, installed separately)

**Environment Variables:**

| Variable | Required | Description |
|---|---|---|
| `OPENAI_API_KEY` | Yes | API key for the OpenAI platform. |

**Launch Command:**

```sh
codex exec --prompt-file <launch_prompt_path>
```

The prompt is consumed from a file path rather than injected post-boot — the
Codex CLI supports `--prompt-file` for multi-line prompts, avoiding
shell-quoting edge cases.

---

### `gemini`

**Binary:** `gemini` (Google Gemini CLI, installed separately)

**Environment Variables:**

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | API key for the Google AI platform. |

**Launch Command:**

```sh
gemini generate --prompt-file <launch_prompt_path>
```

Same file-based prompt delivery as `codex`.

---

## Extending: Registering a New Adapter

Adding a new LLM adapter requires editing exactly one file — `spawn.py` — and
the CLI surface does not change.

### Steps

1. **Add an adapter function** in `src/atdd/coach/commands/spawn.py`:

   ```python
   def _my_llm_adapter(prompt_path: Path) -> str:
       """Return the shell command string that launches the agent session.

       prompt_path: written by cmd_spawn; inject post-boot or pass as argv
       depending on your CLI's conventions.
       """
       _require_env("MY_LLM_API_KEY", "my-llm")
       return f"my-llm-cli --some-flag '{prompt_path}'"
   ```

2. **Register it** in `ADAPTER_REGISTRY`:

   ```python
   ADAPTER_REGISTRY: dict[str, Callable[[Path], str]] = {
       "claude-code": _claude_code_adapter,
       ...
       "my-llm":      _my_llm_adapter,  # add here
   }
   ```

3. **Document it** in this file: add a row to the Registered Adapters table
   and a detail section below.

### Invariants

- The adapter function signature is `(prompt_path: Path) -> str`. Every
  adapter must accept `prompt_path` even if it does not use it.
- Use `_require_env(var, adapter_id)` to raise `AdapterError` early when the
  required env var is absent.
- `ATDD_AGENT_ID` is injected as an env-var prefix by `_inject_agent_env`
  after the adapter runs — adapters do not need to handle this themselves.
- The adapter string is passed to the multiplexer backend as a shell command;
  it must not assume a specific shell other than POSIX `sh`.

---

## Interactive Model Selection

When `atdd coach` spawns a persona it may prompt the operator to pick an LLM
adapter for each role (planner / tester / coder / reviewer). This prompt is
gated by `should_prompt_for_models()` in `spawn.py` and can be bypassed with
`--no-prompt`.

The prompt lists the keys of `ADAPTER_REGISTRY` — this document is the
companion reference that explains what each key means and which env var it
needs.

Pass `--persona-llm <role>=<adapter-id>` to pre-select an adapter without the
interactive prompt:

```sh
atdd coach 664 --persona-llm tester=gemini --persona-llm coder=codex
```

---

## Manifest Backfill

If issues are absent from `.atdd/manifest.yaml` (due to direct `gh issue
create` usage or a dropped stash), run:

```sh
atdd manifest backfill
# equivalent to:
atdd issue reconcile
```

Both routes call `IssueManager.reconcile()`, which fetches all open
`atdd-issue`-labelled GitHub issues and appends missing entries to the manifest.
The operation is idempotent — re-running when the manifest is already complete
is a no-op.
