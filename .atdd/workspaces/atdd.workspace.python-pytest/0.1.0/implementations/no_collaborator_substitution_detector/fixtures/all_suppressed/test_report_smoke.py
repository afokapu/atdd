# URN: test:demo:all-suppressed:SMOKE-001-report-substitutions-all-marked
# Phase: SMOKE
# Layer: integration
"""CRUX fixture: two collaborator substitutions, BOTH suppress-marked. The
detector emits TWO RAW violations (NON-EMPTY) yet the downstream consumer absorbs
both markers -> disposition PASS. The flip happens ENTIRELY in the consumer."""


def _fake_render(rows):
    return "<html/>"


def test_report_smoke(monkeypatch):
    from app.report import ReportService

    service = ReportService()

    monkeypatch.setattr(service, "db", object())  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2099-01-01
    service.render = _fake_render  # atdd:suppress(tester.smoke.no-collaborator-substitution) UNTIL=2099-01-01

    assert service.build("2026-Q2")
