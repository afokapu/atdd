# URN: test:demo:clean:SMOKE-001-login-against-real-boundary
# Phase: SMOKE
# Layer: integration
"""GREEN fixture: a real SMOKE test. Environment setup only (monkeypatch.setenv /
.chdir are exempt); no collaborator substitution -> RAW = [] -> disposition PASS."""


def test_login_drives_real_boundary(monkeypatch, tmp_path):
    # Environment setup is allowed in a smoke test — these are NOT substitutions.
    monkeypatch.setenv("SERVICE_URL", "http://127.0.0.1:8099")
    monkeypatch.chdir(tmp_path)

    from app.login import LoginService

    service = LoginService()
    result = service.authenticate("real-user", "real-pass")
    assert result.ok
