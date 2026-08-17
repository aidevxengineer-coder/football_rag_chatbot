from services.rag_orchestrator.responses import (
    is_kb_refusal,
    kb_miss_message,
    normalize_kb_miss_response,
)


def test_kb_miss_message_offers_web_search_when_disabled():
    msg = kb_miss_message(web_search_enabled=False)
    assert "knowledge base" in msg.lower()
    assert "web search" in msg.lower()
    assert "globe" in msg.lower()


def test_kb_miss_message_when_web_search_enabled():
    msg = kb_miss_message(web_search_enabled=True)
    assert "web search was enabled" in msg.lower()


def test_normalize_replaces_generic_refusal():
    draft = "I'm sorry, I cannot help you with that. Feel free to ask any other football-related questions!"
    result = normalize_kb_miss_response(
        draft,
        web_search_enabled=False,
        chunks=[{"document": "irrelevant"}],
        tool_results=[],
    )
    assert "knowledge base" in result.lower()
    assert "cannot help you with that" not in result.lower()


def test_normalize_empty_context_without_llm_call():
    result = normalize_kb_miss_response(
        "Some answer",
        web_search_enabled=False,
        chunks=[],
        tool_results=[],
    )
    assert "knowledge base" in result.lower()


def test_normalize_keeps_valid_answer():
    draft = "Arsenal used a 4-3-3 formation in 2023/24."
    result = normalize_kb_miss_response(
        draft,
        web_search_enabled=False,
        chunks=[{"document": "formation data"}],
        tool_results=[],
    )
    assert result == draft


def test_is_kb_refusal_detects_common_phrases():
    assert is_kb_refusal("I'm sorry, I cannot help you with that.")
    assert not is_kb_refusal("Liverpool won 2-1.")
