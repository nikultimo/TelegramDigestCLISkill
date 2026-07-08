import pytest

from tg_digest import db, feedback


@pytest.mark.asyncio
async def test_feedback_uses_stored_item_topics_without_llm(tmp_path, monkeypatch):
    db_path = tmp_path / "digest.db"
    db.init_db(db_path)
    db.add_channel(db_path, "https://t.me/s/demo", "demo")
    channel_id = db.list_channels(db_path)[0]["id"]
    post_id = db.insert_post(
        db_path,
        channel_id,
        "1",
        "Text that should not be sent for topic extraction",
        "https://t.me/demo/1",
        "2026-07-08T10:00:00+00:00",
    ).post_id
    item_id = db.insert_digest_item(
        db_path,
        "2026-07-08",
        post_id,
        8.0,
        "read",
        "summary",
        topics=["production ml", "architecture"],
    )

    async def fail_chat(*args, **kwargs):
        raise AssertionError("LLM topic extraction should not run when stored topics exist")

    monkeypatch.setattr(feedback.llm, "chat", fail_chat)

    topics = await feedback.process_feedback(
        item_id,
        1,
        db_path=db_path,
        base_url="http://llm.test/v1",
        api_key="test",
        model="test-model",
    )

    assert topics == ["production ml", "architecture"]
    assert db.get_topic_weights(db_path)["production ml"] == 1.1
