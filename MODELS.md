# Multi-Provider AI CLI Setup

A reproducible setup that gives you one shell-command per AI coding agent, all
under a `claude-<provider>` namespace, so you can swap providers when you hit
quota, want a second opinion, or need a model that's better at a specific task.

> **Filename note:** This file is named `MODELS.md`. The emerging 2026
> convention is `AGENTS.md` (auto-loaded by some tools as context). Pick
> whichever name matches your team's discoverability needs — content is the
> same.

## TL;DR command list

After completing setup, you'll have:

| Command           | Backend                          | Path        | Subscription-backed? |
| ----------------- | -------------------------------- | ----------- | -------------------- |
| `claude`          | Anthropic                        | direct      | Anthropic Pro/Max or API |
| `claude-glm` (`glm`) | z.ai (`api.z.ai`)             | direct      | ✅ z.ai Coding Plan ($18/mo+) |
| `claude-qwen`     | DashScope (Alibaba)              | direct      | ✅ DashScope Coding Plan |
| `claude-deepseek` | DeepSeek                         | direct      | API pay-per-token only |
| `claude-kimi`     | Moonshot (Kimi)                  | direct      | ✅ Moonshot subscription |
| `claude-gpt`      | OpenAI GPT-5                     | via `ccr`   | ❌ API only (Plus doesn't cover) |
| `claude-gemini`   | Google Gemini 3                  | via `ccr`   | Free tier on AI Studio |
| `claude-mistral` (`claude-vibe`) | Mistral / Codestral | via `ccr`   | ❌ Le Chat Pro doesn't cover; free API tier exists |
| `claude-grok`     | xAI Grok-4                       | via `ccr`   | API pay-per-token |

Each `claude-<provider>` is a thin shell function that sets
`ANTHROPIC_BASE_URL` (and friends) before launching `claude`. Real `claude`
keeps hitting `api.anthropic.com` — nothing about the global Claude Code
config changes.

## Architecture

```
        ┌────────────────────────────────────────────────────┐
        │   `claude` binary (Claude Code, version-managed)   │
        └───────────────────────┬────────────────────────────┘
                                │
              ┌─────────────────┼──────────────────────┐
              │                 │                      │
       env vars: untouched   env vars from         env vars from
       (auth via keychain)   `claude-<native>`     `claude-<router>`
              │                 │                      │
              ▼                 ▼                      ▼
        api.anthropic.com   provider's              localhost:3456
                            Anthropic-compat        (claude-code-router)
                            endpoint                      │
                                                          ▼
                                                    OpenAI / Gemini /
                                                    Mistral / xAI ...
```

**Two routing strategies:**

1. **Native** (`claude-glm`, `claude-qwen`, `claude-deepseek`, `claude-kimi`)
   — provider exposes its own Anthropic-compatible endpoint at a public URL.
   We just override `ANTHROPIC_BASE_URL` and `ANTHROPIC_AUTH_TOKEN`. No
   intermediary process.

2. **Via `claude-code-router` (`ccr`)** (`claude-gpt`, `claude-gemini`,
   `claude-mistral`, `claude-grok`) — provider only exposes an
   OpenAI-compatible API. A small local daemon at `127.0.0.1:3456` translates
   between Anthropic and OpenAI wire formats. Same env-var override on Claude
   Code, but pointed at localhost.

## Prerequisites

- **macOS or Linux**, `zsh` as your interactive shell
- **Claude Code** installed (`claude` resolves on `$PATH`)
- **`jq`** (for the optional status-line script)
- **Node.js + npm** (only if you want the router providers)

## Step 1: shell functions

Append the block below to `~/.zshrc`. Open a new terminal (or `source
~/.zshrc`) afterward.

```bash
# claude-<provider> — Claude Code routed to a non-Anthropic backend that
# exposes an Anthropic-compatible endpoint. Real `claude` keeps hitting
# api.anthropic.com. Use `claude-<provider> --resume` to continue an
# Anthropic-side session against the alternate provider after a quota hit.
#
# UPDATE_ME_WHEN_NEW_MODELS: bump the per-provider TOP/FAST IDs below when
# vendors ship newer flagships — none expose an "always-latest" alias.
_provider_key_url() {
  case "$1" in
    glm)      print "https://z.ai/manage-apikey/apikey-list" ;;
    qwen)     print "https://dashscope.console.aliyun.com/" ;;
    deepseek) print "https://platform.deepseek.com/api_keys" ;;
    kimi)     print "https://platform.moonshot.ai/console/api-keys" ;;
    gpt)      print "https://platform.openai.com/api-keys" ;;
    gemini)   print "https://aistudio.google.com/app/apikey" ;;
    mistral)  print "https://console.mistral.ai/api-keys" ;;
    grok)     print "https://console.x.ai/team/default/api-keys" ;;
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

# Router (OpenAI-compat providers, via local claude-code-router daemon).
_ccr_route() {
  local provider="$1" top="$2" key_file="$3" env_var="$4"
  shift 4
  local key=""
  [[ -r "$key_file" ]] && key="$(< "$key_file")"
  local key_was_added=0
  if [[ -z "$key" ]]; then
    _prompt_save_key "$provider" "$key_file" || return 1
    key="$(< "$key_file")"
    key_was_added=1
  fi
  [[ -r "$HOME/.config/openai/api_key"  ]] && export OPENAI_API_KEY="$(<  "$HOME/.config/openai/api_key" )"
  [[ -r "$HOME/.config/google/api_key"  ]] && export GEMINI_API_KEY="$(<  "$HOME/.config/google/api_key" )"
  [[ -r "$HOME/.config/mistral/api_key" ]] && export MISTRAL_API_KEY="$(< "$HOME/.config/mistral/api_key")"
  [[ -r "$HOME/.config/xai/api_key"     ]] && export XAI_API_KEY="$(<     "$HOME/.config/xai/api_key"    )"
  if (( key_was_added )); then
    print "  Restarting ccr to pick up the new $provider key..."
    ccr restart >/dev/null 2>&1
  else
    ccr status >/dev/null 2>&1 || ccr start >/dev/null 2>&1
  fi
  ANTHROPIC_BASE_URL="http://127.0.0.1:3456" \
  ANTHROPIC_AUTH_TOKEN="ccr-local" \
  ANTHROPIC_MODEL="$top" \
  command claude "$@"
}

claude-gpt()     { _ccr_route gpt     "gpt-5"             "$HOME/.config/openai/api_key"  OPENAI_API_KEY  "$@"; }
claude-gemini()  { _ccr_route gemini  "gemini-3-pro"      "$HOME/.config/google/api_key"  GEMINI_API_KEY  "$@"; }
claude-mistral() { _ccr_route mistral "codestral-latest"  "$HOME/.config/mistral/api_key" MISTRAL_API_KEY "$@"; }
claude-grok()    { _ccr_route grok    "grok-4"            "$HOME/.config/xai/api_key"     XAI_API_KEY     "$@"; }

claude-vibe() { claude-mistral "$@"; }
```

## Step 2: install `claude-code-router` (router providers only)

Skip if you only want the native ones.

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
      "name": "openai",
      "api_base_url": "https://api.openai.com/v1/chat/completions",
      "api_key": "${OPENAI_API_KEY}",
      "models": ["gpt-5", "gpt-5-codex", "gpt-5-mini"],
      "transformer": { "use": ["Anthropic"] }
    },
    {
      "name": "gemini",
      "api_base_url": "https://generativelanguage.googleapis.com/v1beta/models/",
      "api_key": "${GEMINI_API_KEY}",
      "models": ["gemini-3-pro", "gemini-3-flash"],
      "transformer": { "use": ["gemini"] }
    },
    {
      "name": "mistral",
      "api_base_url": "https://api.mistral.ai/v1/chat/completions",
      "api_key": "${MISTRAL_API_KEY}",
      "models": ["mistral-large-latest", "codestral-latest", "mistral-small-latest"]
    },
    {
      "name": "xai",
      "api_base_url": "https://api.x.ai/v1/chat/completions",
      "api_key": "${XAI_API_KEY}",
      "models": ["grok-4", "grok-code-fast-1"]
    }
  ],
  "Router": {
    "default": "openai,gpt-5",
    "background": "openai,gpt-5-mini",
    "longContextThreshold": 60000
  }
}
```

The shell functions auto-start `ccr` on first call and `ccr restart` it after
a new key is added. Manual lifecycle: `ccr start | stop | restart | status`.

> ⚠️ `claude-code-router` is community-maintained
> ([musistudio/claude-code-router](https://github.com/musistudio/claude-code-router)),
> not Anthropic. Has solid traction and active maintenance, but standard
> third-party-tool risk applies.

## Step 3: get API keys

You don't have to do them all up front — the shell functions prompt for the
key the first time you invoke each command (silent input, saves to the right
file with `chmod 600`).

If you'd rather pre-seed:

```bash
mkdir -p ~/.config/zai      && chmod 700 ~/.config/zai      && printf '%s' 'YOUR_KEY' > ~/.config/zai/api_key      && chmod 600 ~/.config/zai/api_key
mkdir -p ~/.config/dashscope && chmod 700 ~/.config/dashscope && printf '%s' 'YOUR_KEY' > ~/.config/dashscope/api_key && chmod 600 ~/.config/dashscope/api_key
# ...same shape for deepseek, moonshot, openai, google, mistral, xai
```

> ⚠️ **Do not let the line wrap.** A multi-line copy will run `chmod 600`
> with no argument and leave the file world-readable. Single-line only.

Where to grab keys (provider dashboards):

| Provider  | Dashboard |
| --------- | --------- |
| z.ai      | https://z.ai/manage-apikey/apikey-list |
| DashScope | https://dashscope.console.aliyun.com/ |
| DeepSeek  | https://platform.deepseek.com/api_keys |
| Moonshot  | https://platform.moonshot.ai/console/api-keys |
| OpenAI    | https://platform.openai.com/api-keys |
| Google    | https://aistudio.google.com/app/apikey |
| Mistral   | https://console.mistral.ai/api-keys |
| xAI       | https://console.x.ai/team/default/api-keys |

## Step 4 (optional): visual cue in Claude Code's status line

Distinct color per provider so you always know which model your prompts are
hitting. Drop the script below at `~/.claude/statusline.sh` (`chmod +x`):

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
    gpt-*|*-codex)         badge=$'\033[1;97;42m  GPT · OpenAI  \033[0m' ;;
    gemini-*)              badge=$'\033[1;97;46m  Gemini · Google  \033[0m' ;;
    mistral-*|codestral-*) badge=$'\033[1;30;47m  Mistral  \033[0m' ;;
    grok-*)                badge=$'\033[1;97;40m  Grok · xAI  \033[0m' ;;
    *)                     badge=$'\033[1;97;100m  ccr-router  \033[0m' ;;
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

And register it in `~/.claude/settings.json`:

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
$ claude            # working on something, hits Anthropic quota
^D                  # exit
$ claude-glm --resume   # resume same conversation, now flowing through z.ai
```

Claude Code stores conversation state on disk; `--resume` picks up the last
session regardless of which provider env it was started with. Inside a
running session you can also `/model <id>` to switch among the models the
current backend supports (e.g. `/model glm-5.1` while in `claude-glm`).

## Subscription vs. API billing — read this before paying

Some "subscription" plans cover only the chat product (web/desktop) and
**don't** include API access. Things to know:

| Subscription                | Covers chat | Covers your `claude-<x>` setup? |
| --------------------------- | ----------- | ------------------------------ |
| ChatGPT Plus ($20)          | Yes         | ❌ No (use `codex` for ChatGPT-backed GPT) |
| ChatGPT Pro ($200)          | Yes         | Limited; some included API usage |
| z.ai GLM Coding Plan ($18+) | —           | ✅ Yes — endpoint *is* the subscription |
| DashScope Coding Plan       | —           | ✅ Yes (use `coding-intl` URL) |
| Moonshot subscription       | —           | ✅ Yes (same URL, quota auto-debited) |
| Mistral Le Chat Pro ($15)   | Yes         | ❌ No |
| Anthropic Pro/Max           | Yes         | Yes (via Claude Code OAuth login, separate from `claude-<x>`) |

Rule of thumb: providers built for **chat-first** consumer products (OpenAI,
Mistral) sell two unrelated products. Providers built for **dev-first**
consumption (z.ai, DashScope, Moonshot) bundle subscription with API.

## Troubleshooting

### "Welcome banner says Anthropic, but I set ANTHROPIC_BASE_URL"

Type `/status` inside the session. If it shows your alternate `Anthropic
base URL`, you're routed correctly — the welcome banner is cached identity
data and doesn't reflect the current session's actual provider. The model
saying "I'm Claude" inside the chat is also misleading: Claude Code's system
prompt tells the model to identify as Claude, and most non-Anthropic models
(GLM, Qwen, etc.) play along with that role-play.

Ground truth lives in `/status`'s `Anthropic base URL` line, plus billing
behavior in your provider dashboard.

### `claude-gpt` returns 429 / insufficient_quota

Your OpenAI account has no API credits. ChatGPT Plus/Pro doesn't include
them. Either add billing at
https://platform.openai.com/settings/organization/billing, or use `codex`
(which uses your ChatGPT subscription via "Sign in with ChatGPT").

### Background calls go to z.ai/whatever even though I want Haiku on real Anthropic

Claude Code doesn't support per-model base-URL routing. Once you set
`ANTHROPIC_BASE_URL`, **all** traffic for that process — main model,
small-fast model, background tasks — goes there. The only fix is an
external LLM gateway (LiteLLM etc.) that splits routes per-model. For
typical use, this isn't worth the infra; just remember `claude` itself stays
100% Anthropic.

### Updating model IDs

None of these providers expose an "always-latest" model alias. When a vendor
ships a new flagship (e.g. GLM-6, Qwen 3.6, Codestral 25.x), grep
`UPDATE_ME_WHEN_NEW_MODELS` in your `~/.zshrc` and bump the strings inline.

### Hot-swap mid-session?

Not via the shell-function approach — base URL is read once at process
start. Either exit and re-launch the other `claude-<x>` (using `--resume`),
or use a router (claude-code-router, LiteLLM) that lets `/model <id>` route
on the fly.

## Security checklist

- All key files: `chmod 600`, parent dir `chmod 700`
- Never commit `~/.config/<provider>/` to a dotfiles repo, even an encrypted
  one — the shell function deliberately reads from disk so the keys stay out
  of `~/.zshrc`
- If you use this on a shared machine, also confirm `umask 077` for new files
- The `_prompt_save_key` helper uses `read -rs` (silent) so paste never echoes
  to your terminal scrollback
- The `printf '%s'` (vs `echo`) avoids a trailing newline that some APIs
  reject

## Adding a new provider

If a vendor ships a new Anthropic-compatible endpoint:

1. Add a `claude-<name>()` line invoking `_claude_route` with their URL,
   top model, fast model, and key file path.
2. Add the provider's key dashboard URL to `_provider_key_url`.
3. Add a status-line case in `~/.claude/statusline.sh`.
4. Done — no router or extra infra.

If a vendor only ships an OpenAI-compatible endpoint:

1. Add an entry under `Providers` in `~/.claude-code-router/config.json` with
   their URL and model list.
2. Add a `claude-<name>()` line invoking `_ccr_route` with the model name.
3. Add the dashboard URL to `_provider_key_url`.
4. Add a status-line case in the router branch.
5. `ccr restart` and you're good.
