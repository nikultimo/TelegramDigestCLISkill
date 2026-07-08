---
name: tg-digest
description: >
  Parse public Telegram channels and generate a personalized daily digest
  in Russian Telegram-style sections. Self-learns from like/dislike feedback.
  Use for: syncing channels from account, adding channels, running digest, giving feedback,
  showing preference profile.
triggers:
  - "telegram digest"
  - "tg digest"
  - "add channel"
  - "add telegram channel"
  - "sync channels"
  - "sync telegram"
  - "run digest"
  - "digest feedback"
  - "show digest profile"
  - "tg-digest"
---

# tg-digest Skill

## When to Use
Invoke this skill when the user asks to:
- Sync all subscribed Telegram channels into the digest
- Add or manage individual channels
- Run today's digest (or a dry run)
- Give like/dislike feedback on digest items
- View or reset their topic preference profile

## Prerequisites
```bash
# One-time setup (from project root)
pip install -e .
# .env is already configured with credentials
```

## Commands

| Intent | Command |
|---|---|
| **Sync all subscribed channels** | `tg-digest sync` |
| Add single channel | `tg-digest channel add https://t.me/s/channelname` |
| List channels | `tg-digest channel list` |
| Deactivate channel | `tg-digest channel remove channelname` |
| Run digest (full) | `tg-digest run` |
| Run digest (no TG send) | `tg-digest run --dry-run` |
| Run today's digest only | `tg-digest run --range today` |
| Run last 7 days | `tg-digest run --range days --days 7` |
| Run custom range | `tg-digest run --range custom --from 2026-07-01 --to 2026-07-08` |
| Backfill missing post dates | `tg-digest db backfill-dates` |
| Give positive feedback | `tg-digest feedback <id> like` |
| Give negative feedback | `tg-digest feedback <id> dislike` |
| Show preference profile | `tg-digest profile show` |
| Reset preferences | `tg-digest profile reset --yes` |

## Quickstart Example
```bash
# 1. Sync all your subscribed public channels (interactive login first time)
tg-digest sync

# 2. Run digest
tg-digest run --dry-run

# 3. Give feedback on items
tg-digest feedback 3 like
tg-digest feedback 7 dislike

# 4. Check what was learned
tg-digest profile show
```

## About tg-digest sync
- Uses Telegram MTProto API (Telethon) with your account credentials
- On first run: prompts for your phone number and a one-time code sent by Telegram
- Session is saved to `data/tg_session` — subsequent runs are silent (no re-auth)
- Only syncs **public** channels (those with a username / t.me/s/ URL)
- Private channels are skipped (no public preview URL to scrape)

## How Preferences Work
- Each `like` boosts the topics found in that post by +0.1 (max 2.0×)
- Each `dislike` reduces topic weight by −0.1 (min 0.1×)
- Weights are used in the next `run` to prioritize relevant content
- After ~10 feedbacks the profile becomes meaningful; ~50 makes it stable
- `profile show` prints a table of topics → weights so you can see exactly what was learned

## Output Format
The digest is printed to stdout and saved to `digest_output/YYYY-MM-DD.md`.
By default it includes yesterday + today. Use `--range today`, `--range yesterday`,
`--range days --days N`, or `--range custom --from YYYY-MM-DD --to YYYY-MM-DD`
to choose a different inclusive window.
Digest ranges use Telegram publish dates converted to the local calendar day. Existing
rows with missing dates can be repaired with `tg-digest db backfill-dates`.
Each item looks like:
```
🗓 AI ДАЙДЖЕСТ • 08.07.2026

━━━━━━━━━━━━━━━
📰 ПРОЧИТАТЬ

🔹 Заголовок новости
Короткое объяснение, почему это важно. [1] (https://t.me/channel/1234)
```
Use digest item IDs from generated items when giving feedback with `tg-digest feedback <id> like`.

## Notes
- LLM: any OpenAI-compatible endpoint configured with `OPENAI_BASE_URL`, `OPENAI_API_KEY`, and `OPENAI_MODEL`
- SQLite DB at `data/tg_digest.db` — gitignored, persistent across runs
- Before public release, rotate any token pasted into chat/logs and never stage `.env`, `data/`, `digest_output/`, caches, or `*.egg-info/`
- Schedule with cron: `0 8 * * * cd /path/to/project && tg-digest run`
- Schedule with Claude loop: `/loop 24h tg-digest run`
