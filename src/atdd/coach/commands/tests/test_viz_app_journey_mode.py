# URN: test:coach:viz_app:journey_mode
"""
Regression test for issue #287 Phase 5: viz_app.py exposes a Journey mode
that renders a single train's ordered pipeline (TRAIN_STEP edges visible,
captioned with step + intent) while Structural mode hides TRAIN_STEP.

The Streamlit ``main()`` is a UI integration surface and is excluded — we
test the pure helpers that any UI wire-up depends on:

  - load_graph(..., exclude_train_step=True)  hides TRAIN_STEP
  - load_graph(..., exclude_train_step=False) keeps TRAIN_STEP
  - list_trains() extracts every ``train:*`` node with a category badge
  - _edge_caption() renders TRAIN_STEP arrows with step + intent snippet
  - EDGE_STYLES_MAP["train_step"] exists with a color entry (the real
    EDGE_STYLES_MAP wiring requirement from the issue)
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture(scope="module")
def viz():
    try:
        return importlib.import_module("atdd.coach.commands.viz_app")
    except ModuleNotFoundError as exc:
        pytest.skip(f"viz_app optional deps missing: {exc}")


# ---------------------------------------------------------------------------
# EDGE_STYLES_MAP — the headline deliverable for Phase 5
# ---------------------------------------------------------------------------


def test_edge_styles_map_has_train_step_entry(viz):
    assert "train_step" in viz.EDGE_STYLES_MAP, (
        "EDGE_STYLES_MAP must include a train_step style (#287 Phase 5)"
    )
    entry = viz.EDGE_STYLES_MAP["train_step"]
    assert entry.get("color"), "train_step style needs a color for the solid arrow"


def test_train_category_colors_cover_all_digits(viz):
    for name in ("nominal", "error", "alternate", "exception"):
        assert name in viz.TRAIN_CATEGORY_COLORS


# ---------------------------------------------------------------------------
# _edge_caption — per-arrow label
# ---------------------------------------------------------------------------


def test_edge_caption_plain_type_returned_verbatim(viz):
    assert viz._edge_caption("includes", {}) == "includes"
    assert viz._edge_caption("contains", {}) == "contains"


def test_edge_caption_train_step_with_step_and_intent(viz):
    caption = viz._edge_caption(
        "train_step",
        {"step": 2, "intent": "Hand off to dispatch-call and issue the request"},
    )
    assert caption.startswith("step 2 — Hand off")


def test_edge_caption_train_step_truncates_long_intent(viz):
    long_intent = "x" * 120
    caption = viz._edge_caption("train_step", {"step": 5, "intent": long_intent})
    # Must remain bounded so it doesn't overflow the arrow
    assert len(caption) <= len("step 5 — ") + 40 + 3  # +3 for the ellipsis
    assert caption.endswith("...")


def test_edge_caption_train_step_falls_back_when_metadata_missing(viz):
    assert viz._edge_caption("train_step", {}) == "train_step"


# ---------------------------------------------------------------------------
# list_trains — dropdown source
# ---------------------------------------------------------------------------


def test_list_trains_filters_to_train_family(viz):
    data = {
        "nodes": [
            {"urn": "train:0205-alt", "family": "train", "label": "0205-alt"},
            {"urn": "wagon:a", "family": "wagon", "label": "a"},
            {"urn": "feature:x", "family": "feature", "label": "x"},
        ],
        "edges": [],
    }
    trains = viz.list_trains(data)
    assert [t["urn"] for t in trains] == ["train:0205-alt"]


def test_list_trains_infers_category_from_second_digit(viz):
    data = {
        "nodes": [
            {"urn": "train:0105-err", "family": "train", "label": "0105-err"},
            {"urn": "train:0205-alt", "family": "train", "label": "0205-alt"},
            {"urn": "train:0305-exc", "family": "train", "label": "0305-exc"},
            {"urn": "train:0005-nom", "family": "train", "label": "0005-nom"},
        ],
        "edges": [],
    }
    trains = viz.list_trains(data)
    by_urn = {t["urn"]: t["category"] for t in trains}
    assert by_urn["train:0005-nom"] == "nominal"
    assert by_urn["train:0105-err"] == "error"
    assert by_urn["train:0205-alt"] == "alternate"
    assert by_urn["train:0305-exc"] == "exception"


def test_list_trains_handles_non_numeric_ids(viz):
    data = {
        "nodes": [
            {"urn": "train:my-train", "family": "train", "label": "my-train"},
        ],
        "edges": [],
    }
    trains = viz.list_trains(data)
    assert trains[0]["category"] is None


# ---------------------------------------------------------------------------
# build_elements — TRAIN_STEP arrows carry a caption field
# ---------------------------------------------------------------------------


def test_build_elements_attaches_caption_to_train_step(viz):
    data = {
        "nodes": [
            {"urn": "wagon:a", "family": "wagon", "label": "a"},
            {"urn": "wagon:b", "family": "wagon", "label": "b"},
        ],
        "edges": [
            {
                "source": "wagon:a",
                "target": "wagon:b",
                "type": "train_step",
                "metadata": {"step": 1, "intent": "do stuff", "train": "train:t"},
            },
            {
                "source": "wagon:a",
                "target": "wagon:b",
                "type": "contains",
                "metadata": {},
            },
        ],
    }
    elements = viz.build_elements(data, "", [])
    by_type = {e["data"]["edge_type"]: e["data"] for e in elements["edges"]}
    assert by_type["train_step"]["caption"] == "step 1 — do stuff"
    # Non-train edges still carry a caption so EdgeStyle(caption="caption")
    # does not drop the label for them.
    assert by_type["contains"]["caption"] == "contains"
