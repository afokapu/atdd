# Multi-Provider Claude Code Routing

A reproducible setup that gives you one shell command per AI coding agent —
all under a `claude-<provider>` namespace — so you can swap providers when
you hit quota, want a second opinion, or need a model better suited to a
specific task.

> **History:** this file used to be `MODELS.md`. Renamed to `ROUTERS.md`
> because, after consolidating non-native providers behind OpenRouter, the
> doc is fundamentally about *routing strategies*, not a model catalog. The
> old name is preserved in `git log --follow ROUTERS.md`.

## TL;DR command list

| Command           | Backend                    | Routing path             | Subscription-backed?         |
| ----------------- | -------------------------- | ------------------------ | ---------------------------- |
| `claude`          | Anthropic                  | direct                   | Anthropic Pro/Max or API     |
| `claude-glm` (`glm`) | z.ai                    | direct (native compat)   | ✅ z.ai Coding Plan ($18+/mo) |
| `claude-qwen`     | DashScope (Alibaba)        | direct (native compat)   | ✅ DashScope Coding Plan      |
| `claude-deepseek` | DeepSeek                   | direct (native compat)   | API pay-per-token only       |
| `claude-kimi`     | Moonshot (Kimi)            | direct (native compat)   | ✅ Moonshot subscription      |
| `claude-gpt`      | OpenAI GPT-5.5+            | `ccr` → OpenRouter       | API only (Plus/Pro doesn't cover) |
| `claude-gemini`   | Google Gemini              | `ccr` → OpenRouter       | Free tier on AI Studio       |
| `claude-mistral` (`-vibe`) | Mistral / Codestral | `ccr` → OpenRouter       | Le Chat Pro doesn't cover; free API tier |
| `claude-grok`     | xAI Grok                   | `ccr` → OpenRouter       | API pay-per-token            |

## Architecture — two routing strategies

```
┌─────────────────┐
│   Claude Code   │ Anthropic-shaped /v1/messages requests
│   (TUI binary)  │
└────────┬────────┘
         │ ANTHROPIC_BASE_URL set per command
         │
   ┌─────┴──────────────────────────────────────────────┐
   │                                                    │
   ▼ NATIVE                                             ▼ ROUTED
┌──────────────────┐                          ┌──────────────────────┐
│  api.<vendor>/   │                          │  127.0.0.1:3456      │ LOCAL
│   anthropic      │                          │  claude-code-router  │ daemon
│  (Anthropic-     │                          │  (`ccr` binary)      │
│  compatible)     │                          └──────────┬───────────┘
└──────────────────┘                                     │ OpenAI-shape
   │                                                     │
   ▼                                                     ▼
z.ai / DashScope /              ┌────────────────────────────────────┐
DeepSeek / Moonshot             │  openrouter.ai (CLOUD model gateway)│
(direct, no proxy)              │  + your BYOK keys for upstream      │
                                │  vendor billing                     │
                                └────────────┬───────────────────────┘
                                             │
                                             ▼
                                OpenAI / Google / Mistral / xAI
```

### Two routers, two purposes

There are *two* things called "router" in this stack — keep them straight:

- **`claude-code-router`** (the `ccr` binary) — **local daemon** on
  `127.0.0.1:3456`. Translates Claude Code's Anthropic-shaped requests into
  OpenAI-shaped requests. Required because Claude Code only speaks Anthropic
  format and most non-Anthropic providers only speak OpenAI format.
- **OpenRouter** (`openrouter.ai`) — **cloud model gateway**. One API
  endpoint that fans out to OpenAI, Google, Mistral, xAI, and 100+ others.
  Handles per-vendor quirks (parameter renames, reasoning gymnastics) so
  individual providers don't break Claude Code.

We use both because each solves a different problem:

| Layer | Translates | Why we need it |
|---|---|---|
| `ccr` (local) | Anthropic shape ↔ OpenAI shape | Claude Code can't natively call OpenAI APIs |
| OpenRouter (cloud) | OpenAI shape ↔ each vendor's quirks | Individual vendor APIs drift; we don't want to chase each one |

### Why split into two strategies (native + routed)?

Some providers ship their own Anthropic-compatible endpoint, so we can hit
them directly with one less hop. Others don't, so we bounce through
`ccr` + OpenRouter. The split is determined by the upstream's API surface,
not by us:

| Provider | Anthropic-compat URL? | Strategy |
|---|---|---|
| z.ai | Yes (`api.z.ai/api/anthropic`) | Native |
| DashScope | Yes (`coding-intl.dashscope.aliyuncs.com/apps/anthropic`) | Native |
| DeepSeek | Yes (`api.deepseek.com/anthropic`) | Native |
| Moonshot | Yes (`api.moonshot.ai/anthropic`) | Native |
| OpenAI | No | Routed |
| Google | No | Routed |
| Mistral | No | Routed |
| xAI | No | Routed |

## Prerequisites

- macOS or Linux, `zsh` as your interactive shell
- **Claude Code** installed (`claude` resolves on `$PATH`)
- **`jq`** (for the optional status-line script)
- **Node.js + npm** (only if you want the routed providers)

## Step 1 — shell functions

Append to `~/.zshrc`:

```bash
# claude-<provider> — Claude Code routed to alternate backends.
# UPDATE_ME_WHEN_NEW_MODELS: bump per-provider TOP/FAST IDs when vendors
# ship newer flagships — none expose an "always-latest" alias.

_provider_key_url() {
  case "$1" in
    glm)        print "https://z.ai/manage-apikey/apikey-list" ;;
    qwen)       print "https://dashscope.console.aliyun.com/" ;;
    deepseek)   print "https://platform.deepseek.com/api_keys" ;;
    kimi)       print "https://platform.moonshot.ai/console/api-keys" ;;
    openrouter) print "https://openrouter.ai/keys" ;;
  esac
}

# Interactive prompt-and-save for a missing provider key. Silent input.
_prompt_save_key() {
  local provider="$1" key_file="$2"
  if [[ ! -t 0 ]]; then
    print -u2 "claude-$provider: no key at $key_file (stdin is not a terminal)."
    return 1
  fi
  print "claude-$provider: no key found at $key_file"
  local url; url="$(_provider_key_url "$provider")"
  [[ -n "$url" ]] && print "  Get one at: $url"
  print -n "  Paste key (input hidden, Enter to confirm, Ctrl-C to abort): "
  local key=""
  IFS= read -rs key
  print
  [[ -z "$key" ]] && { print -u2 "  No key entered, aborting."; return 1; }
  mkdir -p "${key_file:h}" && chmod 700 "${key_file:h}"
  printf '%s' "$key" > "$key_file" && chmod 600 "$key_file"
  print "  Saved to $key_file (chmod 600)."
}

# Native (provider has its own Anthropic-compat endpoint).
_claude_route() {
  local provider="$1" base_url="$2" top="$3" fast="$4" key_file="$5"
  shift 5
  local key=""
  [[ -r "$key_file" ]] && key="$(< "$key_file")"
  if [[ -z "$key" ]]; then
    _prompt_save_key "$provider" "$key_file" || return 1
    key="$(< "$key_file")"
  fi
  ANTHROPIC_BASE_URL="$base_url" \
  ANTHROPIC_AUTH_TOKEN="$key" \
  ANTHROPIC_MODEL="$top" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="$top" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="$top" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$fast" \
  command claude "$@"
}

claude-glm()      { _claude_route glm      "https://api.z.ai/api/anthropic"                              "glm-5.1"             "glm-5-turbo"       "$HOME/.config/zai/api_key"       "$@"; }
claude-qwen()     { _claude_route qwen     "https://coding-intl.dashscope.aliyuncs.com/apps/anthropic"   "qwen3.5-plus"        "qwen3-flash"       "$HOME/.config/dashscope/api_key" "$@"; }
claude-deepseek() { _claude_route deepseek "https://api.deepseek.com/anthropic"                          "deepseek-v4-pro[1m]" "deepseek-v4-flash" "$HOME/.config/deepseek/api_key"  "$@"; }
claude-kimi()     { _claude_route kimi     "https://api.moonshot.ai/anthropic"                           "kimi-k2.5"           "moonshot-v1-32k"   "$HOME/.config/moonshot/api_key"  "$@"; }

# Short alias for muscle memory.
glm() { claude-glm "$@"; }

# Routed (via local ccr daemon → OpenRouter → upstream vendor).
# Single key file: ~/.config/openrouter/api_key
_ccr_route() {
  local provider="$1" top="$2" fast="$3"
  shift 3
  local key_file="$HOME/.config/openrouter/api_key"
  local key=""
  [[ -r "$key_file" ]] && key="$(< "$key_file")"
  local key_was_added=0
  if [[ -z "$key" ]]; then
    print "claude-$provider needs an OpenRouter key (one key powers gpt/gemini/mistral/grok)."
    _prompt_save_key openrouter "$key_file" || return 1
    key="$(< "$key_file")"
    key_was_added=1
  fi
  export OPENROUTER_API_KEY="$key"
  if (( key_was_added )); then
    print "  Restarting ccr to pick up the new OpenRouter key..."
    ccr restart >/dev/null 2>&1
  else
    ccr status >/dev/null 2>&1 || ccr start >/dev/null 2>&1
  fi
  ANTHROPIC_BASE_URL="http://127.0.0.1:3456" \
  ANTHROPIC_AUTH_TOKEN="ccr-local" \
  ANTHROPIC_MODEL="$top" \
  ANTHROPIC_DEFAULT_OPUS_MODEL="$top" \
  ANTHROPIC_DEFAULT_SONNET_MODEL="$top" \
  ANTHROPIC_DEFAULT_HAIKU_MODEL="$fast" \
  command claude "$@"
}

claude-gpt()     { _ccr_route gpt     "openai/gpt-5.5"             "openai/gpt-4o-mini"  "$@"; }
claude-gemini()  { _ccr_route gemini  "google/gemini-3-pro"        "google/gemini-3-flash" "$@"; }
claude-mistral() { _ccr_route mistral "mistralai/codestral-latest" "mistralai/codestral-latest" "$@"; }
claude-grok()    { _ccr_route grok    "x-ai/grok-4"                "x-ai/grok-code-fast-1" "$@"; }

claude-vibe() { claude-mistral "$@"; }
```

## Step 2 — install `claude-code-router` (routed providers only)

Skip if you only want the native four.

```bash
npm install -g @musistudio/claude-code-router
mkdir -p ~/.claude-code-router && chmod 700 ~/.claude-code-router
```

Drop the following at `~/.claude-code-router/config.json`:

```json
{
  "LOG": false,
  "API_TIMEOUT_MS": 600000,
  "Providers": [
    {
      "name": "openrouter",
      "api_base_url": "https://openrouter.ai/api/v1/chat/completions",
      "api_key": "${OPENROUTER_API_KEY}",
      "models": [
        "openai/gpt-4o", "openai/gpt-4o-mini",
        "openai/gpt-5", "openai/gpt-5-chat", "openai/gpt-5-codex", "openai/gpt-5-mini", "openai/gpt-5-pro",
        "openai/gpt-5.1", "openai/gpt-5.1-chat", "openai/gpt-5.1-codex", "openai/gpt-5.1-codex-max",
        "openai/gpt-5.2", "openai/gpt-5.2-chat", "openai/gpt-5.2-codex", "openai/gpt-5.2-pro",
        "openai/gpt-5.3-chat", "openai/gpt-5.3-codex",
        "openai/gpt-5.4",
        "openai/gpt-5.5", "openai/gpt-5.5-pro",
        "google/gemini-3-pro", "google/gemini-3-flash",
        "mistralai/mistral-large-latest", "mistralai/codestral-latest",
        "x-ai/grok-4", "x-ai/grok-code-fast-1"
      ],
      "transformer": {
        "use": [
          "openrouter",
          ["maxtoken", { "max_tokens": 16384 }]
        ]
      }
    }
  ],
  "Router": {
    "default": "openrouter,openai/gpt-5.5",
    "background": "openrouter,openai/gpt-4o-mini",
    "longContextThreshold": 60000
  }
}
```

The shell functions auto-start `ccr` on first call and `ccr restart` it
after a new key is added. Manual lifecycle: `ccr start | stop | restart |
status`.

> ⚠️ `claude-code-router` is community-maintained
> ([musistudio/claude-code-router](https://github.com/musistudio/claude-code-router)).
> Active maintenance, large user base, but standard third-party-tool risk.

## Step 3 — OpenRouter signup, BYOK, and credit deposit

Routed providers all flow through OpenRouter. Three pieces of setup:

### 3a. Create an OpenRouter API key

1. Sign up at https://openrouter.ai (GitHub login works).
2. Settings → API Keys → "+ New Key" → name it `claude-code` or similar.
3. Copy the full `sk-or-v1-...` string. *Only shown in full once.*
4. Save to `~/.config/openrouter/api_key` (or let the function prompt you on
   first `claude-gpt` invocation).

### 3b. BYOK your existing keys (recommended)

Without BYOK, OpenRouter charges you their rates + 5% markup and bills your
OpenRouter wallet. With BYOK, OpenRouter forwards using *your* OpenAI /
Google / Mistral / xAI key, and charges go direct to those vendors at
native pricing.

For each provider you want to BYOK:

1. Settings → Integrations → click the provider (e.g. OpenAI).
2. "+ Add key" → paste your existing key.
3. **Toggle "Always use for this provider" to ON.** Without this, OpenRouter
   pre-validates request budgets *as if it might fall back to charging
   you* — which can still cause issues even though BYOK would succeed.
4. Click "Test" to confirm — should say "Connection test passed".

### 3c. Deposit credits on OpenRouter

**Even with BYOK enabled and "Always use" toggled on, OpenRouter still
runs a `max_tokens` × pricing pre-check against your wallet.** If wallet is
$0, the pre-check budget is ~$0.04 (free tier), and any reasonable request
fails with `402: This request requires more credits, or fewer max_tokens.`

Workaround: deposit at least $5 at https://openrouter.ai/credits. The
deposit is a *prepayment* to unlock the pre-check budget; actual billing
still flows direct via BYOK and your wallet ticks down only by OpenRouter's
own transit fees (negligible).

> **Wallet caveat learned the hard way:** the "$X / MONTH limit" shown on
> an API key is a *spending cap*, not a *deposit*. You need real balance in
> the wallet (at https://openrouter.ai/credits) to make any call land.

## Step 4 — provider API keys

The shell functions prompt for the key the first time you invoke each
command (silent input, saves to the right file with `chmod 600`).

Pre-seed manually if you prefer:

```bash
mkdir -p ~/.config/zai      && chmod 700 ~/.config/zai      && printf '%s' 'YOUR_KEY' > ~/.config/zai/api_key      && chmod 600 ~/.config/zai/api_key
mkdir -p ~/.config/dashscope && chmod 700 ~/.config/dashscope && printf '%s' 'YOUR_KEY' > ~/.config/dashscope/api_key && chmod 600 ~/.config/dashscope/api_key
# ... same shape for deepseek, moonshot, openrouter
```

> ⚠️ **Do not let the line wrap.** Multi-line copy will run `chmod 600`
> with no argument and leave the file world-readable. Single-line only.

Where to grab keys:

| Provider       | Dashboard                                         |
| -------------- | ------------------------------------------------- |
| z.ai           | https://z.ai/manage-apikey/apikey-list            |
| DashScope      | https://dashscope.console.aliyun.com/             |
| DeepSeek       | https://platform.deepseek.com/api_keys            |
| Moonshot       | https://platform.moonshot.ai/console/api-keys     |
| OpenRouter     | https://openrouter.ai/keys                        |
| OpenAI (BYOK)  | https://platform.openai.com/api-keys              |
| Google (BYOK)  | https://aistudio.google.com/app/apikey            |
| Mistral (BYOK) | https://console.mistral.ai/api-keys               |
| xAI (BYOK)     | https://console.x.ai/team/default/api-keys        |

## Step 5 (optional) — visual cue in Claude Code's status line

Distinct color per provider so you always know which model your prompts hit.
Drop the script at `~/.claude/statusline.sh` (`chmod +x`):

```bash
#!/usr/bin/env bash
set -u
input=$(cat)
model=$(printf '%s' "$input" | jq -r '.model.display_name // .model.id // "?"' 2>/dev/null)
cwd=$(printf '%s' "$input" | jq -r '.workspace.current_dir // .cwd // ""' 2>/dev/null)
[[ -z "$cwd" ]] && cwd="$PWD"
short_cwd="${cwd/#$HOME/~}"

url="${ANTHROPIC_BASE_URL:-}"
m="${ANTHROPIC_MODEL:-}"
if [[ "$url" == *"127.0.0.1:3456"* || "$url" == *"localhost:3456"* ]]; then
  case "$m" in
    openai/*)     badge=$'\033[1;97;42m  GPT · OpenAI  \033[0m' ;;
    google/*)     badge=$'\033[1;97;46m  Gemini · Google  \033[0m' ;;
    mistralai/*)  badge=$'\033[1;30;47m  Mistral  \033[0m' ;;
    x-ai/*)       badge=$'\033[1;97;40m  Grok · xAI  \033[0m' ;;
    *)            badge=$'\033[1;97;100m  OpenRouter  \033[0m' ;;
  esac
else
  case "$url" in
    *z.ai*)               badge=$'\033[1;97;41m  GLM · z.ai  \033[0m' ;;
    *dashscope*|*aliyun*) badge=$'\033[1;30;43m  Qwen · DashScope  \033[0m' ;;
    *deepseek*)           badge=$'\033[1;97;44m  DeepSeek  \033[0m' ;;
    *moonshot*)           badge=$'\033[1;97;45m  Kimi · Moonshot  \033[0m' ;;
    *)                    badge=$'\033[2;36m● Anthropic\033[0m' ;;
  esac
fi

if [[ -n "$url" && "$url" != *"api.anthropic.com"* ]]; then
  shown_model="${ANTHROPIC_MODEL:-$model}"
else
  shown_model="$model"
fi

printf '%s \033[2m·\033[0m %s \033[2m·\033[0m \033[2m%s\033[0m' \
  "$badge" "$shown_model" "$short_cwd"
```

Register in `~/.claude/settings.json`:

```json
{
  "statusLine": {
    "type": "command",
    "command": "/Users/YOUR_USERNAME/.claude/statusline.sh"
  }
}
```

## Quota-swap workflow

When you hit a rate limit or burn through subscription quota mid-session:

```
$ claude              # working on something, hits Anthropic quota
^D                    # exit
$ claude-glm --resume # continue same conversation, now flowing through z.ai
```

Claude Code stores conversation state on disk; `--resume` picks up the last
session regardless of which provider env it was started with. Inside a
running session you can also `/model <id>` to switch among the models the
current backend supports.

## GPT-5 family compatibility on OpenRouter

Not every GPT-5-family model works through `ccr` → OpenRouter. Claude Code
sends `thinking: {type: "adaptive"}` which the openrouter transformer
translates into `reasoning: null` — and OpenAI's *strictest* reasoning
endpoints reject that with `"Reasoning is mandatory for this endpoint and
cannot be disabled"`.

Empirical results (May 2026):

| Model                              | Status | Notes |
| ---------------------------------- | ------ | ----- |
| `openai/gpt-5.5-pro`               | ✅      | Heaviest, highest cost |
| `openai/gpt-5.5` *(default)*       | ✅      | Latest non-pro flagship |
| `openai/gpt-5.4`                   | ✅      | |
| `openai/gpt-5.3-codex`             | ✅      | Coding-tuned |
| `openai/gpt-5.2-codex`, `5.1-codex` | ✅     | Older codex variants |
| `openai/gpt-5-pro`                 | ✅      | |
| `openai/gpt-5-chat`                | ⚠️      | No tool support; OK for plain chat |
| `openai/gpt-5`, `openai/gpt-5-codex` | ❌    | Mandatory reasoning, router gap |
| `openai/gpt-5-mini`                | ❌      | Same family quirk |
| `openai/gpt-4o`, `openai/gpt-4o-mini` | ✅   | Older fallbacks; we use mini for background |

The default in this setup is `openai/gpt-5.5`. Switch mid-session via
`/model openai/gpt-5.5-pro` etc. The `gpt-5` and `gpt-5-codex` slugs are
listed for completeness so they appear in `/model` autocomplete, but will
fail with the reasoning error if you actually select them.

## Subscription vs. API billing — read this before paying

Some "subscription" plans cover only the chat product (web/desktop) and
**don't** include API access:

| Subscription                | Covers chat | Covers your `claude-<x>`? |
| --------------------------- | ----------- | ------------------------- |
| ChatGPT Plus ($20)          | Yes         | ❌ — use `codex` for ChatGPT-backed GPT |
| ChatGPT Pro ($200)          | Yes         | Limited; some included API usage |
| Mistral Le Chat Pro ($15)   | Yes         | ❌ Codestral via API explicitly excluded |
| z.ai GLM Coding Plan ($18+) | —           | ✅ — endpoint *is* the subscription |
| DashScope Coding Plan       | —           | ✅ (use `coding-intl` URL) |
| Moonshot subscription       | —           | ✅ (same URL, quota auto-debited) |
| Anthropic Pro/Max           | Yes         | Yes (via Claude Code OAuth login, separate from `claude-<x>`) |

Rule of thumb: providers built for **chat-first** consumer products (OpenAI,
Mistral) sell two unrelated products. Providers built for **dev-first**
consumption (z.ai, DashScope, Moonshot) bundle subscription with API.

## Troubleshooting

### "Welcome banner says Anthropic, but I set ANTHROPIC_BASE_URL"

Type `/status` inside the session. The "Anthropic base URL" line is ground
truth. The welcome banner caches identity from the OAuth login and lies in
non-Anthropic sessions. The chat assistant claiming "I'm Claude" is also
misleading: Claude Code's system prompt tells the model to identify as
Claude, and most models comply with that role-play.

### `claude-gpt` returns `402: This request requires more credits…`

Your OpenRouter wallet is empty (or below the request's `max_tokens`
pre-check budget). See Step 3c — deposit at https://openrouter.ai/credits.
The "$X / MONTH limit" on your API key is a *cap*, not a balance.

### `claude-gpt` returns `400: Reasoning is mandatory and cannot be disabled`

You're using one of the strict reasoning models (`openai/gpt-5`,
`openai/gpt-5-codex`). Switch to `openai/gpt-5.5` or another working
variant from the compatibility table above.

### `400: Unsupported parameter: 'max_tokens'`

GPT-5-family quirk via direct OpenAI (not via OpenRouter) — OpenAI renamed
to `max_completion_tokens`. Solution: route through OpenRouter (handled
upstream); see Steps 2 / 3.

### Background calls go to the alternate provider even though I want Haiku on real Anthropic

Claude Code doesn't support per-model base-URL routing. Once you set
`ANTHROPIC_BASE_URL`, **all** traffic for that process goes there. Real
`claude` itself stays 100% Anthropic — the env vars only apply inside
`claude-<x>` functions.

### "9 skill descriptions dropped" warning at session start

Cosmetic. The upstream model's system-prompt budget is smaller than
Anthropic Claude's, so some plugin/skill blurbs get truncated. Skills still
work; you just don't get the auto-catalog.

### Hot-swap mid-session?

`/model <id>` inside a session changes the active model for subsequent
prompts. Limited to models the current backend supports (i.e. exit
`claude-gpt` and start `claude-glm` if you want a different backend; both
processes can reuse the same conversation via `--resume`).

### Updating model IDs

None of the upstream providers expose an "always-latest" alias. When
vendors ship new flagships, grep `UPDATE_ME_WHEN_NEW_MODELS` in `~/.zshrc`
and bump strings inline. For OpenRouter routes, also add the new model to
the `models` array in `~/.claude-code-router/config.json` and update
`Router.default` if you want it as the new default.

## Security checklist

- All key files: `chmod 600`, parent dir `chmod 700`
- Never commit `~/.config/<provider>/` to a dotfiles repo, even encrypted
- The `_prompt_save_key` helper uses `read -rs` (silent) so paste never
  echoes to terminal scrollback
- The `printf '%s'` (vs `echo`) avoids a trailing newline that some APIs
  reject
- BYOK keys live on OpenRouter's servers but never leave their datacenter —
  only the upstream vendor sees them via TLS

## Adding a new provider

If a vendor ships a new Anthropic-compatible endpoint:

1. Add a `claude-<name>()` line invoking `_claude_route` with their URL,
   top model, fast model, and key file path.
2. Add the provider's key dashboard URL to `_provider_key_url`.
3. Add a status-line case in `~/.claude/statusline.sh`.
4. Done — no router or extra infra.

If a vendor only has an OpenAI-compatible endpoint:

1. Add the model IDs (in OpenRouter format like `vendor/model-name`) to the
   `models` array in `~/.claude-code-router/config.json`.
2. Add a `claude-<name>()` line invoking `_ccr_route` with the desired
   default + fast model strings.
3. Add a status-line case in the routed branch.
4. `ccr restart` and you're good.

If the vendor is on OpenRouter, BYOK at openrouter.ai/settings/integrations
to bypass the 5% markup.
