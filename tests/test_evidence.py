from datetime import date, timedelta

import pytest

from customer_intelligence.evidence import canonical_domain, qualifies, validate_assessment
from customer_intelligence.models import Assessment, Profile, Source


def material(app, demo):
    store = app.state.store
    return (
        Assessment.model_validate(demo["brief"]),
        [Source.model_validate(store.get("source", id)) for id in demo["source_ids"]],
        Profile.model_validate(store.get("run", "demo-research")["profile"]),
    )


def test_demo_illustrates_valid_observations_and_hypotheses(app, demo):
    brief, sources, profile = material(app, demo)
    assert validate_assessment(brief, sources, [], profile, demo["domain"]) == []
    assert qualifies(brief)


def test_missing_or_invented_citations_block_a_brief(app, demo):
    brief, sources, profile = material(app, demo)
    brief.why_fits[0].evidence[0].quote = "An invented quote that the original source does not contain."
    assert validate_assessment(brief, sources, [], profile, demo["domain"])


def test_hypotheses_require_explanation_and_names_require_evidence(app, demo):
    brief, sources, profile = material(app, demo)
    brief.who_matters[0].basis.reasoning = None
    brief.who_matters[1].name = "Imaginary Person"
    issues = validate_assessment(brief, sources, [], profile, demo["domain"])
    assert any("reasoning" in issue for issue in issues)
    assert any("named stakeholder" in issue for issue in issues)


def test_stale_timing_is_rejected_and_no_timing_is_valid(app, demo):
    brief, sources, profile = material(app, demo)
    if brief.why_now:
        brief.why_now.event_date = date.today() - timedelta(days=400)
        assert any(
            "stale" in issue for issue in validate_assessment(brief, sources, [], profile, demo["domain"])
        )
    brief.why_now = None
    assert validate_assessment(brief, sources, [], profile, demo["domain"]) == []


def test_exclusions_or_unknown_fit_prevent_recommendation(app, demo):
    brief, _, _ = material(app, demo)
    brief.matched_exclusions = ["Excluded company type"]
    assert not qualifies(brief)
    brief.matched_exclusions = []
    brief.criteria[0].status = "unknown"
    assert not qualifies(brief)


def test_asset_references_must_exist(app, demo):
    brief, sources, profile = material(app, demo)
    brief.what_could_help[0].kind = "asset"
    brief.what_could_help[0].asset_id = "invented-template"
    assert any(
        "asset library" in issue for issue in validate_assessment(brief, sources, [], profile, demo["domain"])
    )


def test_company_domains_are_normalised():
    assert canonical_domain("https://www.company.com/docs") == "company.com"
    with pytest.raises(ValueError):
        canonical_domain("localhost")
