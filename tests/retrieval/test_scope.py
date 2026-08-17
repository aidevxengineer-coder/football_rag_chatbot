from services.rag_orchestrator.retrieval_scope import resolve_retrieval_project_ids
from services.retrieval.dense import GLOBAL_PROJECT_KEY


def test_resolve_user_kb_for_logged_in_chat():
    ids = resolve_retrieval_project_ids(project_id=None, user_id="user-1")
    assert ids == [GLOBAL_PROJECT_KEY, "user_kb:user-1"]


def test_resolve_league_and_user_kb():
    ids = resolve_retrieval_project_ids(project_id="proj-9", user_id="user-1")
    assert ids == [GLOBAL_PROJECT_KEY, "user_kb:user-1", "proj-9"]


def test_resolve_global_for_anonymous():
    ids = resolve_retrieval_project_ids(project_id=None, user_id=None)
    assert ids == [GLOBAL_PROJECT_KEY]
