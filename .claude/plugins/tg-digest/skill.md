---
name: tg-digest
description: >
  Parse public Telegram channels and generate a personalized daily digest
  in Russian Telegram-style sections. Self-learns from like/dislike feedback.
  Use for: syncing channels from account, adding channels, setting or tuning preferences,
  running digest, giving feedback, showing preference profile.
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
  - "tune digest profile"
  - "tg-digest"
---

# tg-digest Skill

## When to Use
Invoke this skill when the user asks to:
- Sync all subscribed Telegram channels into the digest
- Add or manage individual channels
- Run today's digest (or a dry run)
- Set or tune the readable preference profile
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
| First-run preferences | `tg-digest profile init` |
| Set preferences directly | `tg-digest profile set --likes "..." --dislikes "..." --notes "..." --min-score 7.0` |
| Load long profile from file | `tg-digest profile set --likes-file ./profile.md` |
| Tune preferences naturally | `tg-digest profile tune "меньше хайпа, больше production ML"` |
| Reset preferences | `tg-digest profile reset --yes` |

## Quickstart Example
```bash
# 1. Sync all your subscribed public channels (interactive login first time)
tg-digest sync

# 2. Set starting preferences if profile show says there are none
tg-digest profile show
tg-digest profile init

# 3. Run digest
tg-digest run --dry-run

# 4. Give feedback on items
tg-digest feedback 3 like
tg-digest feedback 7 dislike

# 5. Check what was learned
tg-digest profile show
```

## About tg-digest sync
- Uses Telegram MTProto API (Telethon) with your account credentials
- On first run: prompts for your phone number and a one-time code sent by Telegram
- Session is saved to `data/tg_session` — subsequent runs are silent (no re-auth)
- Only syncs **public** channels (those with a username / t.me/s/ URL)
- Private channels are skipped (no public preview URL to scrape)

## How Preferences Work
- A readable profile stores what the user likes, dislikes, extra guidance, and a `min_score` threshold
- On first setup, run `tg-digest profile show`; if no profile exists, ask the user what to prioritize/avoid and run `tg-digest profile init`
- For long Markdown profiles, write them to a file and run `tg-digest profile set --likes-file <path>`
- For casual changes like "поправь рекомендации", prefer `tg-digest profile tune "<request>"`
- Each `like` boosts the topics found in that post by +0.1 (max 2.0×)
- Each `dislike` reduces topic weight by −0.1 (min 0.1×)
- The readable profile is the primary relevance source; feedback weights are only weak fine-tuning
- Digest item IDs are visible as `#N`; use those IDs with `tg-digest feedback <id> like|dislike`
- Posts below `min_score` are dropped before summarization
- `profile show` prints the readable profile plus the topic → weight table

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
