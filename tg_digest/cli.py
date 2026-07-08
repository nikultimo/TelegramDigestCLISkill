import asyncio
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from tg_digest import db, deliver, feedback, filter as filt, scraper, summarizer, tg_sync
from tg_digest.config import get_settings
from tg_digest.ranges import resolve_date_range

app = typer.Typer(help="Personal Telegram channel digest — self-learning, minimal config.")
channel_app = typer.Typer(help="Manage channels.")
app.add_typer(channel_app, name="channel")
profile_app = typer.Typer(help="View and manage preference profile.")
app.add_typer(profile_app, name="profile")
db_app = typer.Typer(help="Database maintenance.")
app.add_typer(db_app, name="db")

console = Console()


def _settings():
    return get_settings()


def _ensure_db():
    s = _settings()
    db.init_db(s.db_path)
    return s


# ── channel commands ──────────────────────────────────────────────────────────

@channel_app.command("add")
def channel_add(url: str = typer.Argument(..., help="Public channel URL (t.me/s/name or t.me/name)")):
    """Add a public Telegram channel."""
    s = _ensure_db()
    name = url.rstrip("/").split("/")[-1].lstrip("@").lower()
    db.add_channel(s.db_path, url, name)
    console.print(f"[green]Added channel:[/green] {name} ({url})")


@channel_app.command("list")
def channel_list():
    """List all tracked channels."""
    s = _ensure_db()
    channels = db.list_channels(s.db_path)
    if not channels:
        console.print("[yellow]No channels added yet.[/yellow] Use: tg-digest channel add <url>")
        return
    t = Table("ID", "Name", "URL", "Active", "Added")
    for ch in channels:
        t.add_row(
            str(ch["id"]), ch["name"], ch["url"],
            "✓" if ch["active"] else "✗", ch["added_at"][:10],
        )
    console.print(t)


@channel_app.command("remove")
def channel_remove(name: str = typer.Argument(..., help="Channel name to deactivate")):
    """Deactivate a channel (stop including in digests)."""
    s = _ensure_db()
    count = db.remove_channel(s.db_path, name)
    if count:
        console.print(f"[yellow]Deactivated:[/yellow] {name}")
    else:
        console.print(f"[red]Channel not found:[/red] {name}")
        raise typer.Exit(1)


# ── run command ───────────────────────────────────────────────────────────────

@app.command("run")
def run_digest(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print digest without sending Telegram message")] = False,
    range_name: Annotated[
        str,
        typer.Option(
            "--range",
            help="Digest window: yesterday-today, today, yesterday, days, or custom",
        ),
    ] = "yesterday-today",
    days: Annotated[int | None, typer.Option("--days", help="Number of days for --range days")] = None,
    from_date: Annotated[str | None, typer.Option("--from", help="Start date for --range custom (YYYY-MM-DD)")] = None,
    to_date: Annotated[str | None, typer.Option("--to", help="End date for --range custom (YYYY-MM-DD)")] = None,
):
    """Scrape channels, build digest, and deliver."""
    asyncio.run(_run_digest(dry_run=dry_run, range_name=range_name, days=days, from_date=from_date, to_date=to_date))


async def _run_digest(
    dry_run: bool,
    range_name: str = "yesterday-today",
    days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> None:
    s = _ensure_db()
    run_date = date.today().isoformat()
    try:
        digest_range = resolve_date_range(
            range_name,
            days=days,
            from_date=from_date,
            to_date=to_date,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    channels = db.get_active_channels(s.db_path)
    if not channels:
        console.print("[yellow]No active channels.[/yellow] Add one: tg-digest channel add <url>")
        return

    console.print(f"[bold]Fetching {len(channels)} channel(s) for {digest_range.label}...[/bold]")
    channel_posts = await scraper.fetch_all_channels(channels, limit=s.scrape_limit)

    # Deduplicate by post ID against DB. Digest candidates are selected from DB by date range.
    new_count = 0
    timestamp_updates = 0
    total_seen = 0
    for ch in channels:
        posts = channel_posts.get(ch["id"], [])
        total_seen += len(posts)
        for p in posts:
            result = db.insert_post(s.db_path, ch["id"], p.post_id, p.text, p.url, p.timestamp or None)
            if result.inserted:
                new_count += 1
            if result.timestamp_updated:
                timestamp_updates += 1

    digest_posts = db.get_posts_for_digest(
        s.db_path,
        digest_range.start.isoformat(),
        digest_range.end.isoformat(),
    )

    console.print(
        f"  {total_seen} posts fetched · {new_count} new · "
        f"{timestamp_updates} timestamps updated · {len(digest_posts)} in range"
    )

    if not digest_posts:
        console.print(f"[green]Nothing new for {digest_range.label}.[/green]")
        return

    weights = db.get_topic_weights(s.db_path)
    console.print(f"[bold]Scoring {len(digest_posts)} posts...[/bold]")
    scored = await filt.score_posts(
        digest_posts, weights,
        base_url=s.openai_base_url,
        api_key=s.openai_api_key,
        model=s.openai_model,
    )

    console.print(f"[bold]Building digest from top {len(scored)} posts...[/bold]")
    items = await summarizer.build_digest(
        scored,
        base_url=s.openai_base_url,
        api_key=s.openai_api_key,
        model=s.openai_model,
    )

    # persist digest items to DB and attach DB IDs
    for item in items:
        post = item.get("_post", {})
        post_db_id = post.get("db_id")
        if post_db_id is None:
            continue
        db_id = db.insert_digest_item(
            s.db_path, run_date, post_db_id,
            post.get("score", 0.0),
            item.get("category", "read"),
            item.get("description", ""),
        )
        item["_db_id"] = db_id

    digest_md = deliver.render_digest(items, digest_range.label, len(channels), total_seen)

    # always write .md file
    md_path = deliver.write_md(digest_md, s.digest_output_dir, digest_range.output_stem)
    console.print(f"[green]Digest saved:[/green] {md_path}")

    console.print("\n" + digest_md)

    if dry_run:
        console.print("\n[yellow]--dry-run: Telegram message not sent.[/yellow]")
    else:
        console.print("[bold]Sending Telegram message...[/bold]")
        try:
            await deliver.send_telegram(digest_md, s.tg_bot_token, s.tg_chat_id)
            console.print("[green]Telegram message sent.[/green]")
        except ValueError as e:
            console.print(f"[red]Telegram skipped:[/red] {e}")
        except Exception as e:
            console.print(f"[red]Telegram send failed:[/red] {e}")


# ── feedback command ──────────────────────────────────────────────────────────

@app.command("feedback")
def give_feedback(
    item_id: int = typer.Argument(..., help="Digest item ID (shown as #N in the digest)"),
    signal: str = typer.Argument(..., help="'like' or 'dislike'"),
):
    """Record feedback on a digest item to train preferences."""
    if signal not in ("like", "dislike"):
        console.print("[red]Signal must be 'like' or 'dislike'[/red]")
        raise typer.Exit(1)
    asyncio.run(_give_feedback(item_id, 1 if signal == "like" else -1))


async def _give_feedback(item_id: int, sig: int) -> None:
    s = _ensure_db()
    try:
        topics = await feedback.process_feedback(
            item_id, sig,
            db_path=s.db_path,
            base_url=s.openai_base_url,
            api_key=s.openai_api_key,
            model=s.openai_model,
        )
        label = "liked" if sig > 0 else "disliked"
        if topics:
            console.print(f"[green]Feedback recorded ({label}).[/green] Topics updated: {', '.join(topics)}")
        else:
            console.print(f"[green]Feedback recorded ({label}).[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


# ── profile commands ──────────────────────────────────────────────────────────

@profile_app.command("show")
def profile_show():
    """Show current topic preference weights."""
    s = _ensure_db()
    weights = db.get_topic_weights(s.db_path)
    if not weights:
        console.print("[yellow]No preferences learned yet.[/yellow] Run digest and give feedback to build your profile.")
        return
    t = Table("Topic", "Weight", "Bias")
    for topic, w in sorted(weights.items(), key=lambda x: -x[1]):
        bias = "[green]prefer[/green]" if w > 1.0 else ("[red]deprioritize[/red]" if w < 1.0 else "neutral")
        t.add_row(topic, f"{w:.2f}", bias)
    console.print(t)


@profile_app.command("reset")
def profile_reset(
    confirm: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
):
    """Reset all topic weights to 1.0."""
    if not confirm:
        typer.confirm("Reset all preference weights?", abort=True)
    s = _ensure_db()
    db.reset_topic_weights(s.db_path)
    console.print("[green]Preferences reset.[/green]")


# ── sync command ──────────────────────────────────────────────────────────────

@app.command("sync")
def sync_channels():
    """
    Sync all public Telegram channels you're subscribed to into the digest.

    Requires TG_API_ID and TG_API_HASH in .env.
    On first run: prompts for your phone number and a one-time code from Telegram.
    Session is saved to TG_SESSION path — subsequent runs are silent.
    """
    s = _ensure_db()
    if not s.tg_api_id or not s.tg_api_hash:
        console.print("[red]TG_API_ID and TG_API_HASH must be set in .env[/red]")
        raise typer.Exit(1)

    console.print("[bold]Connecting to Telegram (interactive login on first run)...[/bold]")
    asyncio.run(_sync_channels(s))


async def _sync_channels(s) -> None:
    existing_urls = {ch["url"] for ch in db.list_channels(s.db_path)}
    channels, added = await tg_sync.sync_channels_to_db(
        api_id=s.tg_api_id,
        api_hash=s.tg_api_hash,
        session_path=s.tg_session,
        db_path=s.db_path,
    )

    t = Table("Channel", "Title", "URL", "Status")
    for ch in sorted(channels, key=lambda c: c.name):
        status = "[green]new[/green]" if ch.url not in existing_urls else "[dim]existing[/dim]"
        t.add_row(ch.name, ch.title, ch.url, status)
    console.print(t)
    console.print(f"\n[green]{added} new channel(s) added.[/green] Total public channels: {len(channels)}")
    if added == 0 and channels:
        console.print("[dim]All channels already tracked.[/dim]")


@db_app.command("backfill-dates")
def db_backfill_dates():
    """Re-fetch active channel previews and backfill missing Telegram publish dates."""
    asyncio.run(_db_backfill_dates())


async def _db_backfill_dates() -> None:
    s = _ensure_db()
    channels = db.get_active_channels(s.db_path)
    if not channels:
        console.print("[yellow]No active channels.[/yellow] Add one: tg-digest channel add <url>")
        return

    console.print(f"[bold]Backfilling publish dates from {len(channels)} channel(s)...[/bold]")
    channel_posts = await scraper.fetch_all_channels(channels, limit=s.scrape_limit)
    total_seen = 0
    timestamp_updates = 0
    for ch in channels:
        posts = channel_posts.get(ch["id"], [])
        total_seen += len(posts)
        for p in posts:
            result = db.insert_post(s.db_path, ch["id"], p.post_id, p.text, p.url, p.timestamp or None)
            if result.timestamp_updated:
                timestamp_updates += 1

    console.print(
        f"[green]Backfill complete:[/green] {total_seen} posts checked · "
        f"{timestamp_updates} timestamps updated"
    )


if __name__ == "__main__":
    app()
