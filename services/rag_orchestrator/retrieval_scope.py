GLOBAL_PROJECT_KEY = "__global__"


def resolve_retrieval_project_ids(
    *,
    project_id: str | None,
    user_id: str | None,
) -> list[str]:
    """Default global KB is always searched; user Ball Knowledge and leagues add scopes."""
    scopes: list[str] = [GLOBAL_PROJECT_KEY]
    if user_id:
        user_scope = f"user_kb:{user_id}"
        if user_scope not in scopes:
            scopes.append(user_scope)
    if project_id and project_id not in scopes:
        scopes.append(project_id)
    return scopes
