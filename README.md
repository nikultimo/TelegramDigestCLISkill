# tg-digest

Personal Telegram channel digest agent. Scrapes public channels, ranks posts with an LLM,
groups them into Russian Telegram-style sections, and self-learns from your feedback.

Works as a Claude Code skill, Codex/Hermes agent tool, or standalone CLI.

## Features

- Zero Telegram credentials — scrapes public `/s/` preview pages
- Any OpenAI-compatible LLM (OpenAI, Ollama, Hermes, LM Studio, Claude proxy)
- Self-learning: `like`/`dislike` feedback adjusts topic weights for future runs
- Dual delivery: Telegram DM + local `.md` file
- Semantic deduplication: same story from multiple channels → one item, all sources cited
- Russian digest format with compact sections, separators, and visible source links
- Minimal config: one `.env` file, one SQLite DB, one CLI

## Quick Start

```bash
# 1. Install
pip install -e .

# 2. Configure
cp .env.example .env
# Edit .env — set OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL at minimum

# 3. Add channels
tg-digest channel add https://t.me/s/rustlang
tg-digest channel add https://t.me/s/golang
tg-digest channel add https://t.me/s/hackernewsfeed

# 4. Set your starting preferences
tg-digest profile init

# 5. Test with dry run
tg-digest run --dry-run

# 6. Give feedback
tg-digest feedback 3 like
tg-digest feedback 7 dislike

# 7. See what was learned
tg-digest profile show
```

## Installation

Requires Python 3.11+.

```bash
git clone <repo>
cd telegram_agent
pip install -e .
```

## Configuration

Copy `.env.example` to `.env` and fill in:

```env
OPENAI_BASE_URL=https://api.openai.com/v1   # or http://localhost:11434/v1 for Ollama
OPENAI_API_KEY=sk-...                        # or "ollama" for local
OPENAI_MODEL=gpt-4o-mini                     # or mistral, hermes-3, llama3, etc.

TG_BOT_TOKEN=...    # optional — from @BotFather
TG_CHAT_ID=...      # optional — your chat ID from @userinfobot

TG_API_ID=0         # optional — only for tg-digest sync, from https://my.telegram.org/apps
TG_API_HASH=...     # optional — only for tg-digest sync
TG_SESSION=./data/tg_session

SCRAPE_LIMIT=20               # optional — max posts to fetch per channel per run
DIGEST_OUTPUT_DIR=./digest_output  # optional — where .md digests are saved
DB_PATH=./data/tg_digest.db   # optional — SQLite store location

# TG_DIGEST_HOME=/path/to/telegram_agent  # optional — project root when running from another directory
```

Relative paths (`DB_PATH`, `DIGEST_OUTPUT_DIR`, `TG_SESSION`) resolve against
the project root, not the current directory. With an editable install
(`pip install -e .`) the root is detected automatically; otherwise set
`TG_DIGEST_HOME` so agents and scripts can run `tg-digest` from anywhere.

To get your Telegram bot token:
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the token into `TG_BOT_TOKEN`

To get your chat ID:
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy the `Id` field into `TG_CHAT_ID`

## Command Reference

```bash
# Sync all subscribed public channels from your Telegram account (⚠️ requires human TTY)
tg-digest sync

# Channel management
tg-digest channel add https://t.me/s/channelname
tg-digest channel list
tg-digest channel remove channelname

# Run digest
tg-digest run              # default window: yesterday + today
tg-digest run --dry-run    # same but skip Telegram send
tg-digest run --range today
tg-digest run --range yesterday
tg-digest run --range days --days 7
tg-digest run --range custom --from 2026-07-01 --to 2026-07-08

# Maintenance
tg-digest check              # verify env vars, DB, and active channels
tg-digest db backfill-dates  # repair missing Telegram publish dates in existing DB rows

# Feedback (train preferences)
tg-digest feedback <id> like
tg-digest feedback <id> dislike

# Preference profile
tg-digest profile init     # first-run interactive preferences (⚠️ requires human TTY)
tg-digest profile show     # readable profile + learned topic weights
tg-digest profile set --likes "production ML" --dislikes "crypto hype"
tg-digest profile set --likes-file ./profile.md
tg-digest profile tune "меньше AI tool lists, больше production ML"
tg-digest profile reset --yes  # reset readable profile and learned weights
```

## How Recommendations Work

`tg-digest profile init` stores a readable preference profile in SQLite:
what you like, what you dislike, extra guidance, and a minimum relevance score
for inclusion in the digest. The default minimum score is `7.0`. If no profile is
saved yet, scoring falls back to a broad personal profile covering practical AI,
backend/highload, career/money, English, health/style, games/lore, travel, cars,
and useful tech.

The readable profile is the primary relevance signal. Learned topic weights from
feedback are only a weak secondary signal for fine-tuning:

| Action | Effect |
|---|---|
| `like` | Topics stored for that digest item +0.1 weight (max 2.0×) |
| `dislike` | Topics stored for that digest item −0.1 weight (min 0.1×) |

Scored topics are saved with each digest item, so feedback usually does not need a
second LLM topic-extraction pass. Posts below your `min_score` are dropped before
summarization, so weak matches are not forced into the digest. If more than 20
posts pass the threshold, only the top 20 by score are included in a single
digest — the rest remain in the DB and can surface in a later run.

Use `tg-digest profile set` for exact edits, or `tg-digest profile tune "..."` for
natural-language adjustments through the configured LLM — including digest volume:
"показывай больше" lowers the `min_score` threshold, "make it stricter" raises it.
Digest item IDs are shown
as `#42` in the output and can be used with `tg-digest feedback 42 like|dislike`.

## Digest Date Ranges

By default, `tg-digest run` includes posts from yesterday and today. Date windows are
inclusive and use the Telegram post publish date converted to the local calendar day.
Rows without a Telegram publish date are skipped until they are repaired by a later scrape
or `tg-digest db backfill-dates`.

```bash
tg-digest run --range today
tg-digest run --range yesterday
tg-digest run --range days --days 7
tg-digest run --range custom --from 2026-07-01 --to 2026-07-08
```

Posts already included in a previous digest item are not resurfaced in later runs.

## Output Format

Digest output is generated in Russian and formatted for Telegram readability:

```text
🗓 AI ДАЙДЖЕСТ • 08.07.2026

━━━━━━━━━━━━━━━
📰 ПРОЧИТАТЬ

🔹 Заголовок новости
Короткое объяснение, почему это важно. [1] (https://t.me/channel/1234)
```

The source URLs stay visible in the text so the same `.md` file is easy to read locally.

## Public Release Checklist

Before pushing this repository publicly:

1. Rotate any bot/API tokens that were pasted into chat, logs, or local shell history.
2. Confirm private runtime files are ignored: `.env`, `data/`, `digest_output/`, caches, build outputs, and egg-info.
3. Run `tg-digest db backfill-dates` before generating a real digest from an existing local DB.
4. Run `tg-digest run --dry-run` and inspect dates/sources before enabling Telegram delivery.
5. Verify with `pip install -e ".[dev]"`, then `python -m pytest -q` and `python -m compileall -q tg_digest`.

GitHub Actions (`.github/workflows/ci.yml`) runs the same pytest + compileall
check on every push and pull request, on Python 3.11 and 3.12.

## Scheduling

### Cron
```bash
crontab -e
# Add:
0 8 * * * cd /path/to/telegram_agent && /path/to/venv/bin/tg-digest run
```

### Systemd timer
```ini
# ~/.config/systemd/user/tg-digest.service
[Unit]
Description=Telegram Digest

[Service]
WorkingDirectory=/path/to/telegram_agent
ExecStart=/path/to/venv/bin/tg-digest run
EnvironmentFile=/path/to/telegram_agent/.env

# ~/.config/systemd/user/tg-digest.timer
[Unit]
Description=Run tg-digest daily

[Timer]
OnCalendar=*-*-* 08:00:00
Persistent=true

[Install]
WantedBy=timers.target
```
```bash
systemctl --user enable --now tg-digest.timer
```

### Claude Code loop
```
/loop 24h run digest
```

## Using with AI Agents

The canonical skill lives at `skills/tg-digest/SKILL.md` and follows the open
[Agent Skills](https://agentskills.io) standard (`name` + `description`
frontmatter, folder-per-skill), so any skills-compatible agent can use it.

| Runner | How to use |
|---|---|
| **Claude Code** | Picked up via `.claude/skills/tg-digest/SKILL.md` (symlink to the canonical skill) — auto-triggers on "run digest", "add channel", etc. |
| **hermes-agent** | `ln -s /path/to/telegram_agent/skills/tg-digest ~/.hermes/skills/tg-digest` |
| **OpenClaw** | `ln -s /path/to/telegram_agent/skills/tg-digest ~/.openclaw/skills/tg-digest` |
| **Codex / OpenCode** | Reads `AGENTS.md` automatically — call CLI commands directly |
| **Cron / scripts** | `tg-digest run` with env vars set |

Agents that run commands from their own workspace should set
`TG_DIGEST_HOME=/path/to/telegram_agent` in the environment so `.env`, the
SQLite DB, and the output directory resolve to this project (not needed with
an editable install).

## Architecture

```
scraper.py   → fetch /s/ HTML, parse posts
filter.py    → LLM scores posts against readable profile + topic_weights
summarizer.py → LLM deduplicates + classifies into 4 categories
deliver.py   → render Markdown, write file, send Telegram DM
feedback.py  → LLM extracts topics, update topic_weights in SQLite
profile.py   → readable preference profile tuning helpers
db.py        → SQLite: channels, posts, digest_items(+topics), feedback, preference_profile, topic_weights
llm.py       → thin httpx OpenAI-compatible client (no SDK)
config.py    → pydantic-settings, loads .env
cli.py       → typer CLI wiring all above
```

## License

MIT
