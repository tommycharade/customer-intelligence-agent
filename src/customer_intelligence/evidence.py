import re
from datetime import date
from urllib.parse import urlparse

from .models import Assessment, Profile, Source


def normalise(text):
    return " ".join(text.split()).casefold()


def canonical_domain(value):
    parsed = urlparse(value if "://" in value else "https://" + value)
    host = (parsed.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}", host):
        raise ValueError("Enter a company domain such as company.com")
    return host


def validate_links(links, sources):
    problems = []
    for link in links:
        source = sources.get(link.source_id)
        if not source or normalise(link.quote) not in normalise(source.text):
            problems.append(f"Citation {link.source_id} does not match a retrieved excerpt.")
    return problems


def validate_assessment(
    assessment: Assessment, sources: list[Source], assets: list[Source], profile: Profile, domain: str
):
    issues = []
    source_map = {source.id: source for source in sources}
    if canonical_domain(assessment.domain) != domain:
        issues.append("The assessment refers to a different company domain.")
    if {item.criterion for item in assessment.criteria} != {"company_type", "technology", "workflow"} or len(
        assessment.criteria
    ) != 3:
        issues.append("Assess each of the three fit criteria exactly once.")
    for criterion in assessment.criteria:
        issues += validate_links(criterion.evidence, source_map)
        if criterion.status == "supported" and not criterion.evidence:
            issues.append("A supported fit criterion needs evidence.")
    claims = assessment.why_fits + [person.basis for person in assessment.who_matters]
    if assessment.why_now:
        claims.append(assessment.why_now)
        trigger = assessment.why_now
        if trigger.kind != "fact" or not trigger.event_date:
            issues.append("A timing signal must be a dated fact, or why_now must be null.")
        elif not 0 <= (date.today() - trigger.event_date).days <= profile.trigger_days:
            issues.append("The timing signal is stale or future-dated; use no timing signal found.")
    for claim in claims:
        issues += validate_links(claim.evidence, source_map)
        if claim.kind == "hypothesis" and not claim.reasoning:
            issues.append("A hypothesis needs its reasoning and uncertainty explained.")
    if {person.role for person in assessment.who_matters} != {"user", "champion", "budget_holder"} or len(
        assessment.who_matters
    ) != 3:
        issues.append("Include the likely user, champion and budget holder exactly once.")
    for person in assessment.who_matters:
        if person.name and not any(
            normalise(person.name) in normalise(link.quote) for link in person.basis.evidence
        ):
            issues.append("A named stakeholder must appear in their supporting excerpt.")
    asset_ids = {asset.id for asset in assets}
    for action in assessment.what_could_help:
        if action.kind == "asset" and action.asset_id not in asset_ids:
            issues.append("A suggested existing asset must be in the uploaded asset library.")
        if action.kind != "asset" and action.asset_id:
            issues.append("Only an existing asset may have an asset reference.")
    return issues


def qualifies(assessment):
    return (
        assessment.fit in {"strong", "plausible"}
        and not assessment.matched_exclusions
        and all(item.status == "supported" for item in assessment.criteria)
        and any(item.kind == "fact" for item in assessment.why_fits)
    )


def rank_key(account):
    brief = account["brief"]
    return (
        brief["fit"] == "strong",
        bool(brief["why_now"]),
        sum(item["kind"] == "fact" for item in brief["why_fits"]),
    )
