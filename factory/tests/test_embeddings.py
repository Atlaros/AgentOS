from __future__ import annotations

from factory_os.domain.embeddings import (
    _parse_cohere_embeddings,
    embed_dims,
    embed_document,
    embed_query,
    hashed_embedding,
    live_cohere_enabled,
)


def test_pytest_does_not_call_live_cohere(monkeypatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "should-not-use")
    monkeypatch.delenv("FACTORY_OS_LIVE_EMBED", raising=False)
    assert live_cohere_enabled() is False
    text = "blusa crepe oficina"
    assert embed_query(text) == hashed_embedding(text, embed_dims())
    assert embed_document(text) == hashed_embedding(text, embed_dims())


def test_cohere_payload_uses_search_types(monkeypatch) -> None:
    monkeypatch.setenv("COHERE_API_KEY", "test-key")
    monkeypatch.setenv("FACTORY_OS_LIVE_EMBED", "1")
    monkeypatch.setenv("COHERE_EMBED_DIMS", "1024")
    seen: list[str] = []

    def fake_batch(texts: list[str], *, input_type: str) -> list[list[float]]:
        seen.append(input_type)
        return [[0.01] * 1024 for _ in texts]

    monkeypatch.setattr("factory_os.domain.embeddings._cohere_embed_batch", fake_batch)
    query = embed_query("ropa de oficina")
    docs = embed_document("blusa crepe manga larga")
    assert seen == ["search_query", "search_document"]
    assert len(query) == 1024
    assert len(docs) == 1024


def test_parse_cohere_float_block() -> None:
    parsed = _parse_cohere_embeddings({"embeddings": {"float": [[1.0, 0.0], [0.0, 1.0]]}})
    assert parsed == [[1.0, 0.0], [0.0, 1.0]]
