from services.llm_gateway.token_budget import (
    build_context_text_within_budget,
    count_tokens,
    fit_llm_input,
    fit_messages_for_prompt,
    trim_preserve_edges,
)


def test_trim_preserve_edges_keeps_start_and_end():
    text = "ALPHA " + ("middle " * 200) + "OMEGA"
    trimmed = trim_preserve_edges(text, 40)
    assert "ALPHA" in trimmed
    assert "OMEGA" in trimmed
    assert count_tokens(trimmed) <= 40


def test_fit_messages_prefers_recent_turns():
    messages = [
        {"role": "user", "content": "old question"},
        {"role": "assistant", "content": "old answer"},
        {"role": "user", "content": "latest question"},
    ]
    rendered = fit_messages_for_prompt(messages, max_tokens=30)
    assert "latest question" in rendered
    assert count_tokens(rendered) <= 30


def test_build_context_text_keeps_all_chunks_within_budget():
    chunks = [
        {
            "chunk_id": f"c{i}",
            "document": f"fact-{i} " + ("detail " * 80),
            "rrf_score": 1.0 / (i + 1),
        }
        for i in range(8)
    ]
    context = build_context_text_within_budget(chunks, max_tokens=500)
    for i in range(8):
        assert f"c{i}" in context
    assert count_tokens(context) <= 500


def test_fit_llm_input_caps_user_prompt():
    system = "system prompt"
    user = "x" * 20000
    fitted = fit_llm_input(
        system_prompt=system,
        user_prompt=user,
        max_input_tokens=200,
    )
    assert count_tokens(fitted) <= 200 - count_tokens(system)
