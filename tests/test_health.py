"""Deployment readiness: /health must respond 200 with no auth (hosting
platforms poll it to know the process is up), and must not leak anything
about the app's internals."""


def test_health_returns_200_without_login(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_health_body_is_minimal_and_leaks_nothing(client):
    resp = client.get("/health")
    body = resp.get_data(as_text=True)
    assert len(body) < 20
    assert "traceback" not in body.lower()
    assert "flask" not in body.lower()
