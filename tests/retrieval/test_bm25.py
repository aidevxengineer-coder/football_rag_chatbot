import os

from services.retrieval.bm25 import BM25Store


def test_bm25_search_ranks_by_keyword_overlap():
    store = BM25Store()
    store.add_chunks(
        chunk_ids=["chunk_001", "chunk_002", "chunk_003"],
        corpus=[
            "Messi scored twice against Real Madrid.",
            "Ronaldo won the Champions League.",
            "Messi assists helped Barcelona win the title.",
        ],
        project_ids=[None, None, None],
        metadatas=[{}, {}, {}],
    )

    results = store.search("Messi scored", top_k=2)

    assert len(results) == 2
    assert results[0]["chunk_id"] == "chunk_001"


def test_bm25_respects_top_k():
    store = BM25Store()
    corpus = [f"Document about player {i}" for i in range(10)]
    store.add_chunks(
        chunk_ids=[f"chunk_{i:03d}" for i in range(10)],
        corpus=corpus,
        project_ids=[None] * 10,
        metadatas=[{}] * 10,
    )

    results = store.search("player", top_k=3)
    assert len(results) == 3


def test_bm25_save_and_load(tmp_path):
    save_path = str(tmp_path / "bm25.pkl")
    store = BM25Store()
    store.add_chunks(
        chunk_ids=["1", "2", "3"],
        corpus=["First document", "Second document", "Third document"],
        project_ids=[None, None, None],
        metadatas=[{}, {}, {}],
    )
    store.save(save_path)
    assert os.path.exists(save_path)

    loaded = BM25Store()
    assert loaded.load(save_path)
    results = loaded.search("Second", top_k=1)
    assert results[0]["chunk_id"] == "2"


def test_bm25_load_corrupt_file_returns_false(tmp_path):
    save_path = str(tmp_path / "bm25.pkl")
    with open(save_path, "wb") as f:
        f.write(b"truncated")

    loaded = BM25Store()
    assert loaded.load(save_path) is False
    assert loaded.is_loaded() is False


def test_bm25_filters_by_project_id():
    store = BM25Store()
    store.add_chunks(
        chunk_ids=["g1", "p1"],
        corpus=["global football news", "project alpha tactics"],
        project_ids=[None, "proj-a"],
        metadatas=[{"project_id": None}, {"project_id": "proj-a"}],
    )

    global_hits = store.search("football", top_k=5, project_id=None)
    project_hits = store.search("tactics", top_k=5, project_id="proj-a")

    assert [r["chunk_id"] for r in global_hits] == ["g1"]
    assert [r["chunk_id"] for r in project_hits] == ["p1"]
