"""Live cutover smoke test — requires web (:3000), gateway (:8000), and tools (:8088)."""
import sys

import httpx

CHECKS: list[tuple[str, bool, str]] = []


def record(name: str, ok: bool, detail: str) -> None:
    CHECKS.append((name, ok, detail))


def main() -> int:
    client = httpx.Client(timeout=10.0)

    def get(url: str):
        r = client.get(url)
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.status_code, r.json()
        return r.status_code, r.text

    def post(url: str, body: dict):
        r = client.post(url, json=body)
        if r.headers.get("content-type", "").startswith("application/json"):
            return r.status_code, r.json()
        return r.status_code, r.text

    # Tools service
    status, body = get("http://127.0.0.1:8088/health")
    record("tools /health", status == 200 and body.get("status") == "ok", str(body))

    status, body = get("http://127.0.0.1:8088/tools")
    names = [t["name"] for t in body.get("data", [])]
    record("tools GET /tools", status == 200 and "web_search" in names, f"tools={names}")

    status, body = get("http://127.0.0.1:8088/tools/health")
    record(
        "tools GET /tools/health",
        status == 200 and "mcp_available" in body.get("data", {}),
        str(body.get("data")),
    )

    # Gateway
    status, body = get("http://127.0.0.1:8000/health")
    record("gateway /health", status == 200 and body.get("status") == "ok", str(body))

    status, body = get("http://127.0.0.1:8000/tools")
    names = [t["name"] for t in body.get("data", [])]
    record("gateway GET /tools (proxy)", status == 200 and "web_search" in names, f"tools={names}")

    status, body = post(
        "http://127.0.0.1:8000/tools/execute",
        {"tool": "web_search", "arguments": {"query": "x"}},
    )
    record("gateway POST /tools/execute returns 501", status == 501, f"status={status}")

    status, body = get("http://127.0.0.1:8000/")
    record(
        "gateway GET / (API-only)",
        status == 200 and body.get("service") == "gateway",
        str(body),
    )

    # Pitchside web
    status, body = get("http://127.0.0.1:3000/")
    record(
        "web GET / (Pitchside HTML)",
        status == 200 and "<html" in str(body).lower(),
        f"status={status}",
    )

    print("=== LIVE SMOKE TEST ===")
    passed = 0
    for name, ok, detail in CHECKS:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}")
        if ok:
            passed += 1
    print(f"--- {passed}/{len(CHECKS)} passed ---")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
