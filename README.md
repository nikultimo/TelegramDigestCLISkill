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

# 4. Test with dry run
tg-digest run --dry-run

# 5. Give feedback
tg-digest feedback 3 like
tg-digest feedback 7 dislike

# 6. See what was learned
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
```

To get your Telegram bot token:
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow prompts
3. Copy the token into `TG_BOT_TOKEN`

To get your chat ID:
1. Message [@userinfobot](https://t.me/userinfobot)
2. Copy the `Id` field into `TG_CHAT_ID`

## Command Reference

```bash
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
tg-digest db backfill-dates  # repair missing Telegram publish dates in existing DB rows

# Feedback (train preferences)
tg-digest feedback <id> like
tg-digest feedback <id> dislike

# Preference profile
tg-digest profile show     # table of topic → weight
tg-digest profile reset    # reset all to 1.0
```

## How Self-Learning Works

Each `like` or `dislike` triggers topic extraction via the LLM, then updates weights:

| Action | Effect |
|---|---|
| `like` | Topics in that post +0.1 weight (max 2.0×) |
| `dislike` | Topics in that post −0.1 weight (min 0.1×) |

These weights are passed to the scoring prompt on each `run`, biasing the LLM toward
your preferred topics. After ~10 feedbacks the profile is meaningful; ~50 makes it stable.

`tg-digest profile show` lets you see and reason about what was learned. If the agent
misclassified a topic preference, `profile reset` starts fresh.

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
5. Verify with `python -m pytest -q` and `python -m compileall -q tg_digest`.

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

## Agent Compatibility

| Runner | How to use |
|---|---|
| **Claude Code** | Skill auto-triggers on "run digest", "add channel", etc. |
| **Codex / OpenCode** | Reads `AGENTS.md` automatically — call CLI commands directly |
| **Hermes / local agents** | Same as Codex — `AGENTS.md` describes all commands |
| **Cron / scripts** | `tg-digest run` with env vars set |

## Architecture

```
scraper.py   → fetch /s/ HTML, parse posts
filter.py    → LLM scores posts against topic_weights
summarizer.py → LLM deduplicates + classifies into 4 categories
deliver.py   → render Markdown, write file, send Telegram DM
feedback.py  → LLM extracts topics, update topic_weights in SQLite
db.py        → SQLite: channels, posts, digest_items, feedback, topic_weights
llm.py       → thin httpx OpenAI-compatible client (no SDK)
config.py    → pydantic-settings, loads .env
cli.py       → typer CLI wiring all above
```

## License

MIT
