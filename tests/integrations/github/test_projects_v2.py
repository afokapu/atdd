"""Fixture-based tests for ``atdd.integrations.github.projects_v2`` (no live API).

``sync_status_field`` is the dedicated PROJECT_TOKEN-authenticated mutation that
closes #882. These tests prove (a) it refuses to run without the PAT and (b) it
emits the correct single-select mutation when the PAT is present.
"""
from __future__ import annotations

import pytest

from atdd.integrations.github import _gh, projects_v2
from atdd.integrations.github.types import MissingProjectTokenError

ISSUE = 891
PROJECT_ID = "PVT_kw123"
ITEM_ID = "PVTI_item891"
FIELD_ID = "PVTF_status"
OPTION_COMPLETE = "opt_complete"


def test_sync_status_field_requires_project_token(monkeypatch):
    monkeypatch.delenv(_gh.PROJECT_TOKEN_ENV, raising=False)
    with pytest.raises(MissingProjectTokenError):
        projects_v2.sync_status_field(ISSUE, "COMPLETE")


def _install_fake_graphql(monkeypatch):
    """Wire a fake GraphQL backend; return the recorder list of queries."""
    monkeypatch.setenv(_gh.PROJECT_TOKEN_ENV, "ghp_fake_pat")
    monkeypatch.setattr(
        _gh, "resolve_project_config",
        lambda repo_root=None: _gh.ProjectRef(repo="o/r", project_id=PROJECT_ID),
    )
    queries = []

    def fake_graphql(query, *, token=None):
        queries.append((query, token))
        if "projectItems" in query:
            return {"data": {"repository": {"issue": {"projectItems": {
                "nodes": [{"id": ITEM_ID, "project": {"id": PROJECT_ID}}]
            }}}}}
        if "fields(first" in query:
            return {"data": {"node": {"fields": {"nodes": [
                {"id": FIELD_ID, "name": "ATDD Status", "options": [
                    {"id": "opt_init", "name": "INIT"},
                    {"id": OPTION_COMPLETE, "name": "COMPLETE"},
                ]},
            ]}}}}
        return {"data": {"updateProjectV2ItemFieldValue": {
            "projectV2Item": {"id": ITEM_ID}}}}

    monkeypatch.setattr(_gh, "graphql", fake_graphql)
    return queries


def test_sync_status_field_emits_single_select_mutation(monkeypatch):
    queries = _install_fake_graphql(monkeypatch)

    projects_v2.sync_status_field(ISSUE, "COMPLETE")

    mutation = next(q for q, _ in queries if "updateProjectV2ItemFieldValue" in q)
    assert f'itemId: "{ITEM_ID}"' in mutation
    assert f'fieldId: "{FIELD_ID}"' in mutation
    assert f'singleSelectOptionId: "{OPTION_COMPLETE}"' in mutation
    # Every call must be authenticated with the PROJECT_TOKEN PAT (the #882 fix).
    assert all(token == "ghp_fake_pat" for _, token in queries)


def test_sync_status_field_unknown_phase_raises(monkeypatch):
    _install_fake_graphql(monkeypatch)
    with pytest.raises(_gh.GitHubIntegrationError):
        projects_v2.sync_status_field(ISSUE, "NONEXISTENT")
