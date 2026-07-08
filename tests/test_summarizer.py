from tg_digest import summarizer


def test_summarizer_prompt_requires_russian_output_and_keeps_internal_categories():
    prompt = summarizer._SUMMARIZE_PROMPT

    assert "title" in prompt
    assert "description" in prompt
    assert "на русском" in prompt.lower()
    assert '"do"' in prompt
    assert '"learn"' in prompt
    assert '"read"' in prompt
    assert '"practice"' in prompt
