from pathlib import Path

from tg_digest import db


def test_init_db_migrates_existing_posts_table_with_published_at(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)

    with db.get_conn(db_path) as conn:
        columns = [row["name"] for row in conn.execute("PRAGMA table_info(posts)").fetchall()]

    assert "published_at" in columns


def test_readding_removed_channel_reactivates_it(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    db.remove_channel(db_path, "demo")

    db.add_channel(db_path, "https://t.me/s/demo", "demo")

    channels = db.list_channels(db_path)
    assert len(channels) == 1
    assert channels[0]["active"] == 1


def test_get_posts_for_digest_filters_by_published_date_and_excludes_digest_items(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]

    old_id = db.insert_post(db_path, channel_id, "1", "old", "https://t.me/demo/1", "2026-07-06T20:59:00+00:00").post_id
    first_id = db.insert_post(db_path, channel_id, "2", "first", "https://t.me/demo/2", "2026-07-07T00:00:00+00:00").post_id
    second_id = db.insert_post(db_path, channel_id, "3", "second", "https://t.me/demo/3", "2026-07-08T12:00:00+00:00").post_id
    seen_id = db.insert_post(db_path, channel_id, "4", "seen", "https://t.me/demo/4", "2026-07-08T13:00:00+00:00").post_id
    db.insert_digest_item(db_path, "2026-07-08", seen_id, 8.0, "read", "seen already")

    posts = db.get_posts_for_digest(db_path, "2026-07-07", "2026-07-08")

    assert [post["db_id"] for post in posts] == [first_id, second_id]
    assert all(post["db_id"] != old_id for post in posts)
    assert all(post["db_id"] != seen_id for post in posts)
    assert posts[0]["channel"] == "demo"
    assert posts[0]["timestamp"] == "2026-07-07T00:00:00+00:00"


def test_duplicate_insert_backfills_missing_published_at(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]

    first = db.insert_post(db_path, channel_id, "1", "text", "https://t.me/demo/1", None)
    second = db.insert_post(
        db_path,
        channel_id,
        "1",
        "text",
        "https://t.me/demo/1",
        "2026-07-08T10:00:00+00:00",
    )

    post = db.get_post(db_path, first.post_id)
    assert first.inserted is True
    assert second.inserted is False
    assert second.timestamp_updated is True
    assert post["published_at"] == "2026-07-08T10:00:00+00:00"


def test_duplicate_insert_does_not_overwrite_existing_published_at(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]

    first = db.insert_post(
        db_path,
        channel_id,
        "1",
        "text",
        "https://t.me/demo/1",
        "2026-07-08T10:00:00+00:00",
    )
    second = db.insert_post(
        db_path,
        channel_id,
        "1",
        "text",
        "https://t.me/demo/1",
        "2026-07-09T10:00:00+00:00",
    )

    post = db.get_post(db_path, first.post_id)
    assert second.inserted is False
    assert second.timestamp_updated is False
    assert post["published_at"] == "2026-07-08T10:00:00+00:00"


def test_get_posts_for_digest_excludes_unknown_publish_dates(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]

    db.insert_post(db_path, channel_id, "1", "unknown", "https://t.me/demo/1", None)

    assert db.get_posts_for_digest(db_path, "2026-07-08", "2026-07-08") == []


def test_get_posts_for_digest_uses_moscow_local_date(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]

    post = db.insert_post(
        db_path,
        channel_id,
        "1",
        "late UTC",
        "https://t.me/demo/1",
        "2026-07-07T22:30:00+00:00",
    )

    assert db.get_posts_for_digest(db_path, "2026-07-07", "2026-07-07") == []
    assert [row["db_id"] for row in db.get_posts_for_digest(db_path, "2026-07-08", "2026-07-08")] == [post.post_id]


def test_preference_profile_round_trip(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)

    db.save_preference_profile(
        db_path,
        likes_text="production ML, architecture writeups",
        dislikes_text="crypto hype, shallow tool lists",
        notes_text="Prefer posts with numbers and real cases.",
        min_score=7.5,
    )

    profile = db.get_preference_profile(db_path)
    assert profile == {
        "likes_text": "production ML, architecture writeups",
        "dislikes_text": "crypto hype, shallow tool lists",
        "notes_text": "Prefer posts with numbers and real cases.",
        "min_score": 7.5,
    }


def test_reset_preferences_clears_profile_and_topic_weights(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.save_preference_profile(
        db_path,
        likes_text="backend",
        dislikes_text="crypto",
        notes_text="deep dives",
        min_score=8.0,
    )
    db.upsert_topic_weight(db_path, "backend", 1.4)

    db.reset_preferences(db_path)

    assert db.get_preference_profile(db_path) is None
    assert db.get_topic_weights(db_path) == {}


def test_upsert_topic_weight_clamps_to_bounds(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)

    db.upsert_topic_weight(db_path, "overhyped", 5.0)
    db.upsert_topic_weight(db_path, "deprioritized", -3.0)

    weights = db.get_topic_weights(db_path)
    assert weights["overhyped"] == 2.0
    assert weights["deprioritized"] == 0.1


def test_digest_item_round_trips_scored_topics(tmp_path: Path):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]
    post_id = db.insert_post(
        db_path,
        channel_id,
        "1",
        "Agent architecture case study",
        "https://t.me/demo/1",
        "2026-07-08T10:00:00+00:00",
    ).post_id

    item_id = db.insert_digest_item(
        db_path,
        "2026-07-08",
        post_id,
        8.5,
        "read",
        "summary",
        topics=["ai agents", "architecture"],
    )

    assert db.get_digest_item(db_path, item_id)["topics"] == ["ai agents", "architecture"]
