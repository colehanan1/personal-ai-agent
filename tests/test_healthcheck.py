from milton_orchestrator import healthcheck


class DummyResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


def test_healthcheck_all_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_URL", "http://llm")
    monkeypatch.setenv("WEAVIATE_URL", "http://weaviate")
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")

    def fake_get(url, headers=None, timeout=2):
        return DummyResponse(200)

    monkeypatch.setattr(healthcheck.requests, "get", fake_get)

    checks = healthcheck.run_checks(repo_root=tmp_path)
    assert all(check.status == "OK" for check in checks)
    assert healthcheck.overall_ok(checks)


def test_healthcheck_required_failure(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_API_URL", "http://llm")
    monkeypatch.setenv("WEAVIATE_URL", "http://weaviate")
    monkeypatch.setenv("MILTON_MEMORY_BACKEND", "jsonl")

    def fake_get(url, headers=None, timeout=2):
        return DummyResponse(503)

    monkeypatch.setattr(healthcheck.requests, "get", fake_get)

    checks = healthcheck.run_checks(repo_root=tmp_path)
    assert not healthcheck.overall_ok(checks)
