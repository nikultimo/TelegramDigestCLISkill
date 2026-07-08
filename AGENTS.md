# tg-digest — Agent Instructions

This project is a personal daily digest CLI for public Telegram channels.
It scrapes `/s/` preview pages (no auth), ranks posts via an LLM, and delivers
a Russian Telegram-style grouped digest to Telegram DM and a `.md` file.
It self-learns topic preferences from like/dislike feedback.

## One-time Setup

```bash
pip install -e .
cp .env.example .env
# Fill in: OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL
# Optional: TG_BOT_TOKEN, TG_CHAT_ID
```

## Required Env Vars

| Variable | Description | Example |
|---|---|---|
| `OPENAI_BASE_URL` | Any OpenAI-compatible endpoint | `https://api.openai.com/v1` |
| `OPENAI_API_KEY` | API key | `sk-...` or `ollama` |
| `OPENAI_MODEL` | Model name | `gpt-4o-mini`, `mistral`, `hermes-3` |
| `TG_BOT_TOKEN` | Telegram bot token (optional) | from @BotFather |
| `TG_CHAT_ID` | Your Telegram chat ID (optional) | message @userinfobot |
| `TG_API_ID` | Telegram account API ID for `sync` (optional) | from https://my.telegram.org/apps |
| `TG_API_HASH` | Telegram account API hash for `sync` (optional) | from https://my.telegram.org/apps |

Optional:
- `SCRAPE_LIMIT` — max posts per channel per run (default: 20)
- `DIGEST_OUTPUT_DIR` — where to save .md files (default: `./digest_output`)
- `DB_PATH` — SQLite path (default: `./data/tg_digest.db`)
- `TG_SESSION` — Telethon session path for `sync` (default: `./data/tg_session`)

## Common Agent Tasks

### Sync all subscribed public channels (one-time / periodic) — ⚠️ requires human input
```bash
# Interactive on first run — prompts for phone number + OTP
tg-digest sync
```

### Add a single channel manually
```bash
tg-digest channel add https://t.me/s/rustlang
```

### Run digest
```bash
tg-digest run --dry-run
```

Default window is yesterday + today. Other supported windows:
```bash
tg-digest run --range today
tg-digest run --range yesterday
tg-digest run --range days --days 7
tg-digest run --range custom --from 2026-07-01 --to 2026-07-08
tg-digest db backfill-dates
```

### Run full digest (with Telegram send)
```bash
tg-digest run
```

### Set or tune starting preferences
```bash
# For automated agents — use profile set directly (no TTY required):
tg-digest profile set --likes "production ML, backend architecture" --dislikes "crypto hype"
tg-digest profile tune "меньше AI tool lists, больше production ML кейсов"
# For interactive first-time setup (requires human TTY): ⚠️
tg-digest profile init
```

### Give feedback on an item
```bash
tg-digest feedback 42 like
tg-digest feedback 17 dislike
```

### View learned preferences
```bash
tg-digest profile show
```

### Reset preferences
```bash
tg-digest profile reset --yes
```

## Full Command Reference

```
tg-digest sync                       Sync all subscribed public channels from your TG account
tg-digest channel add <url>          Add a single public channel
tg-digest channel list               List all channels
tg-digest channel remove <name>      Deactivate a channel
tg-digest run [--dry-run]            Run digest; default range is yesterday + today
tg-digest run --range today          Run digest for today only
tg-digest run --range days --days 7  Run digest for the last 7 days
tg-digest check                      Verify env vars, DB, and active channels are configured
tg-digest db backfill-dates          Repair missing Telegram publish dates in existing posts
tg-digest feedback <id> like|dislike Record feedback and update preferences
tg-digest profile init               First-run interactive readable preferences (⚠️ requires human TTY)
tg-digest profile show               Print readable profile and topic weights
tg-digest profile set [...]          Edit readable profile fields directly, including --likes-file
tg-digest profile tune <request>     Adjust readable profile with natural language
tg-digest profile reset [--yes]      Reset readable profile and topic weights
```

## File Layout

```
tg_digest/          Python package (scraper, filter, summarizer, deliver, feedback, profile, db, llm, config)
digest_output/      Daily .md digests (YYYY-MM-DD.md) — gitignored
data/tg_digest.db   SQLite store — gitignored
.env                Secrets — gitignored
.env.example        Template for .env
.claude/plugins/tg-digest/skill.md   Claude Code skill definition
```

## Documentation Sync Rule

`AGENTS.md` is the canonical agent instruction file. `CLAUDE.md` must be a
symlink to `AGENTS.md`, not a copied file, so Claude Code and other agents read
the same source of truth.

When changing code, CLI behavior, configuration, database behavior, digest
format, scheduling, tests, tools, or skills, update every affected document in
the same change. Check these files before finishing:

- `README.md` — user-facing setup, commands, behavior, scheduling, output format
- `AGENTS.md` / `CLAUDE.md` — agent-facing operational instructions
- `.claude/plugins/tg-digest/skill.md` — Claude skill commands and usage notes
- `.env.example` — env vars and defaults
- `pyproject.toml` — dependencies, entrypoints, supported Python version

If a document is intentionally unchanged, mention that in the final response.
Do not leave stale command examples, old output formats, obsolete env vars, or
outdated agent workflow notes.

## Public Release Safety

Before committing or publishing this repository:

- Treat any token pasted into chat/logs as compromised; rotate it before public use
- Never stage `.env`, `data/`, `digest_output/`, caches, build outputs, or `*.egg-info/`
- Check staged files for real API keys, Telegram bot tokens, session files, and SQLite data
- Keep `CLAUDE.md` as a symlink to `AGENTS.md`
- Run `python -m pytest -q` and `python -m compileall -q tg_digest`
- If packaging metadata changes, update `pyproject.toml`, `README.md`, and this file together

## Scheduling

**Cron (Linux/Mac):**
```bash
# Daily at 08:00
0 8 * * * cd /path/to/telegram_agent && tg-digest run
```

**Claude Code loop:**
```
/loop 24h run digest
```

**Systemd timer:** See README.md for a complete systemd unit example.

## Notes for Agents

- All LLM calls use JSON mode — responses are structured and parseable
- The SQLite DB is the source of truth; digest item IDs in the output are DB row IDs
- `--dry-run` is safe to use anytime; it writes the `.md` file but skips Telegram
- Digest date ranges use Telegram post publish dates converted to the local calendar day and skip unknown-date posts until backfilled
- Readable preferences live in SQLite `preference_profile`; learned feedback weights live in `topic_weights`
- Digest items store scored topics; feedback uses those topics first and only falls back to LLM extraction for old rows
- The readable profile is the primary relevance source; topic weights are only weak fine-tuning
- `run` drops scored posts below the profile `min_score` threshold before summarization
- Digest output is Russian, with emoji section headers, visible item IDs like `#42`, `━━━━━━━━━━━━━━━` separators, and visible sources like `[1] (https://t.me/channel/1234)`
- The scraper only supports public channels (those with a `t.me/s/` preview URL)
- `tg-digest check` verifies env vars, DB, and active channels — safe to call anytime, no LLM calls
- `tg-digest sync` and `tg-digest profile init` require human TTY input; automated agents should use `tg-digest channel add` and `tg-digest profile set` instead
- On first run with no preferences, ask the user what they want/avoid and save it with `tg-digest profile init` (interactive); in automated context use `tg-digest profile set --likes "..." --dislikes "..."` directly; if skipped, scoring falls back to general software engineering value
