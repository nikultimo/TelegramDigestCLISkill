import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


LOCAL_TZ = ZoneInfo("Europe/Moscow")


@dataclass(frozen=True)
class InsertPostResult:
    post_id: int
    inserted: bool
    timestamp_updated: bool = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS channels (
                id       INTEGER PRIMARY KEY,
                url      TEXT NOT NULL UNIQUE,
                name     TEXT NOT NULL,
                added_at TEXT NOT NULL,
                active   INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS posts (
                id         INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL REFERENCES channels(id),
                post_id    TEXT NOT NULL,
                text       TEXT,
                url        TEXT NOT NULL,
                published_at TEXT,
                scraped_at TEXT NOT NULL,
                UNIQUE(channel_id, post_id)
            );

            CREATE TABLE IF NOT EXISTS digest_items (
                id       INTEGER PRIMARY KEY,
                run_date TEXT NOT NULL,
                post_id  INTEGER NOT NULL REFERENCES posts(id),
                score    REAL NOT NULL,
                category TEXT NOT NULL,
                summary  TEXT NOT NULL,
                included INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS feedback (
                id             INTEGER PRIMARY KEY,
                digest_item_id INTEGER NOT NULL REFERENCES digest_items(id),
                signal         INTEGER NOT NULL,
                created_at     TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS topic_weights (
                topic      TEXT PRIMARY KEY,
                weight     REAL NOT NULL DEFAULT 1.0,
                updated_at TEXT NOT NULL
            );
        """)
        _migrate_posts_published_at(conn)


def _migrate_posts_published_at(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(posts)").fetchall()}
    if "published_at" not in columns:
        conn.execute("ALTER TABLE posts ADD COLUMN published_at TEXT")


@contextmanager
def get_conn(db_path: Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── channels ──────────────────────────────────────────────────────────────────

def add_channel(db_path: Path, url: str, name: str) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO channels (url, name, added_at, active) VALUES (?, ?, ?, 1)
               ON CONFLICT(url) DO UPDATE SET name = excluded.name, active = 1""",
            (url, name, _now()),
        )


def list_channels(db_path: Path) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, url, name, added_at, active FROM channels ORDER BY added_at"
        ).fetchall()
    return [dict(r) for r in rows]


def remove_channel(db_path: Path, name: str) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "UPDATE channels SET active = 0 WHERE name = ? AND active = 1", (name,)
        )
    return cur.rowcount


def get_active_channels(db_path: Path) -> list[dict]:
    with get_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT id, url, name FROM channels WHERE active = 1"
        ).fetchall()
    return [dict(r) for r in rows]


# ── posts ─────────────────────────────────────────────────────────────────────

def insert_post(
    db_path: Path,
    channel_id: int,
    post_id: str,
    text: str,
    url: str,
    published_at: str | None = None,
) -> int | None:
    """Insert post and backfill missing publish time for existing rows."""
    with get_conn(db_path) as conn:
        try:
            cur = conn.execute(
                """INSERT INTO posts (channel_id, post_id, text, url, published_at, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (channel_id, post_id, text, url, published_at, _now()),
            )
            return InsertPostResult(cur.lastrowid, inserted=True)
        except sqlite3.IntegrityError:
            row = conn.execute(
                """SELECT id, published_at FROM posts
                   WHERE channel_id = ? AND post_id = ?""",
                (channel_id, post_id),
            ).fetchone()
            if row is None:
                raise
            timestamp_updated = False
            if published_at and not row["published_at"]:
                conn.execute(
                    "UPDATE posts SET published_at = ? WHERE id = ?",
                    (published_at, row["id"]),
                )
                timestamp_updated = True
            return InsertPostResult(row["id"], inserted=False, timestamp_updated=timestamp_updated)


def get_post(db_path: Path, post_db_id: int) -> dict | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_db_id,)).fetchone()
    return dict(row) if row else None


def get_posts_for_digest(db_path: Path, start_date: str, end_date: str) -> list[dict]:
    """Return undigested posts whose publish date falls inside the inclusive range."""
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            """SELECT p.id AS db_id, c.name AS channel, p.text, p.url,
                      p.published_at AS timestamp, p.scraped_at
               FROM posts p
               JOIN channels c ON c.id = p.channel_id
               WHERE c.active = 1
                 AND p.published_at IS NOT NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM digest_items di WHERE di.post_id = p.id
                 )
               ORDER BY p.published_at, p.id""",
        ).fetchall()

    posts: list[dict] = []
    for row in rows:
        post = dict(row)
        effective = _local_date_from_iso(post["timestamp"])
        if start <= effective <= end:
            posts.append({
                "db_id": post["db_id"],
                "channel": post["channel"],
                "text": post["text"] or "",
                "url": post["url"],
                "timestamp": post.get("timestamp") or post["scraped_at"],
            })
    return posts


def _date_from_iso(value: str) -> date:
    return _local_date_from_iso(value)


def _local_date_from_iso(value: str) -> date:
    value = value.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(LOCAL_TZ).date()


# ── digest items ──────────────────────────────────────────────────────────────

def insert_digest_item(
    db_path: Path, run_date: str, post_db_id: int, score: float, category: str, summary: str
) -> int:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO digest_items (run_date, post_id, score, category, summary) VALUES (?, ?, ?, ?, ?)",
            (run_date, post_db_id, score, category, summary),
        )
        return cur.lastrowid


def get_digest_item(db_path: Path, item_id: int) -> dict | None:
    with get_conn(db_path) as conn:
        row = conn.execute(
            """SELECT di.*, p.text, p.url, p.channel_id
               FROM digest_items di JOIN posts p ON p.id = di.post_id
               WHERE di.id = ?""",
            (item_id,),
        ).fetchone()
    return dict(row) if row else None


# ── feedback ──────────────────────────────────────────────────────────────────

def insert_feedback(db_path: Path, digest_item_id: int, signal: int) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO feedback (digest_item_id, signal, created_at) VALUES (?, ?, ?)",
            (digest_item_id, signal, _now()),
        )


# ── topic weights ─────────────────────────────────────────────────────────────

def get_topic_weights(db_path: Path) -> dict[str, float]:
    with get_conn(db_path) as conn:
        rows = conn.execute("SELECT topic, weight FROM topic_weights").fetchall()
    return {r["topic"]: r["weight"] for r in rows}


def upsert_topic_weight(db_path: Path, topic: str, weight: float) -> None:
    weight = max(0.1, min(2.0, weight))
    with get_conn(db_path) as conn:
        conn.execute(
            """INSERT INTO topic_weights (topic, weight, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(topic) DO UPDATE SET weight = excluded.weight, updated_at = excluded.updated_at""",
            (topic, weight, _now()),
        )


def reset_topic_weights(db_path: Path) -> None:
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM topic_weights")
