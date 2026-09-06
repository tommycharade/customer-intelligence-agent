from datetime import date, timedelta

from .models import (
    Assessment,
    Claim,
    Criterion,
    Evidence,
    HelpfulAction,
    Profile,
    Settings,
    Source,
    Stakeholder,
    now,
)


def seed_demo(store):
    run_id = "demo-research"
    if store.get("run", run_id):
        return run_id
    profile = Profile(
        offering="A workflow review and template for keeping infrastructure and service ownership aligned.",
        company_type="B2B software companies with an internal platform team",
        technology="Terraform and Kubernetes",
        buyer_role="Head of Platform Engineering",
        problem="Manual reconciliation of infrastructure and service ownership",
        buying_trigger="A platform-team expansion or infrastructure migration",
        exclusions=["Consultancies", "Companies without an internal platform team"],
    )
    ids = []
    for index, (name, domain, subtitle) in enumerate(
        [
            (
                "Northstar Labs",
                "northstar.example",
                "A platform expansion with a clearly documented workflow",
            ),
            ("Aster Software", "aster.example", "Strong workflow fit; timing is still an open question"),
            (
                "Pineworks Cloud",
                "pineworks.example",
                "A migration creates a useful opening for a conversation",
            ),
        ]
    ):
        account_id = f"demo-account-{index}"
        when = (date.today() - timedelta(days=7 + index * 5)).isoformat()
        workflow = f"{name} is a B2B software company. Our internal platform team manages Terraform and Kubernetes. Teams currently compare Terraform state with the service ownership catalogue by hand during release reviews."
        trigger = f"On {when}, {name} announced an expansion of its platform engineering team to support an infrastructure migration."
        sources = [
            Source(
                id=f"demo-source-{index}-workflow",
                title=f"{name} · engineering handbook",
                text=workflow,
                source_type="documentation",
                origin="demo",
                account_domain=domain,
                is_demo=True,
                content_hash=f"demo-{index}",
            ),
            Source(
                id=f"demo-source-{index}-trigger",
                title=f"{name} · team update",
                text=trigger,
                source_type="job",
                origin="demo",
                account_domain=domain,
                is_demo=True,
                published_at=when,
                content_hash=f"demo-trigger-{index}",
            ),
        ]
        for source in sources:
            store.put("source", source.id, source)
        evidence = Evidence(source_id=sources[0].id, quote=workflow)
        brief = Assessment(
            company_name=name,
            domain=domain,
            summary=subtitle,
            fit="plausible" if index == 2 else "strong",
            criteria=[
                Criterion(criterion=criterion, status="supported", evidence=[evidence])
                for criterion in ["company_type", "technology", "workflow"]
            ],
            matched_exclusions=[],
            why_fits=[
                Claim(
                    text="An internal platform team runs Terraform and Kubernetes for a B2B software product.",
                    kind="fact",
                    evidence=[evidence],
                ),
                Claim(
                    text="Release reviews include a manual comparison of infrastructure state and service ownership.",
                    kind="fact",
                    evidence=[evidence],
                ),
                Claim(
                    text="A shared ownership-check template could reduce the effort involved in those reviews.",
                    kind="hypothesis",
                    evidence=[evidence],
                    reasoning="The workflow is documented; its cost and the team's appetite for changing it need confirmation.",
                ),
            ],
            why_now=Claim(
                text="The company announced a platform-team expansion tied to an infrastructure migration.",
                kind="fact",
                evidence=[Evidence(source_id=sources[1].id, quote=trigger)],
                event_date=date.fromisoformat(when),
            )
            if index != 1
            else None,
            who_matters=[
                Stakeholder(
                    role=role,
                    title=title,
                    confidence="medium" if role == "user" else "low",
                    basis=Claim(
                        text=reason,
                        kind="hypothesis",
                        evidence=[evidence],
                        reasoning="The handbook identifies the workflow, not the individual decision-makers. Confirm this role in conversation.",
                    ),
                )
                for role, title, reason in [
                    (
                        "user",
                        "Platform engineer",
                        "Likely to perform the infrastructure and ownership checks.",
                    ),
                    (
                        "champion",
                        "Head of Platform",
                        "May own the process and advocate for a more consistent review.",
                    ),
                    (
                        "budget_holder",
                        "VP Engineering",
                        "May sponsor changes that span engineering teams; budget ownership is unconfirmed.",
                    ),
                ]
            ],
            what_could_help=[
                HelpfulAction(
                    kind="proposed_asset",
                    title="A 20-minute ownership-review walkthrough",
                    reason="Walk through one release using a sample Terraform-to-service checklist. Ask where the current process takes time before proposing a solution.",
                )
            ],
        )
        account = {
            "id": account_id,
            "name": name,
            "domain": domain,
            "brief": brief.model_dump(mode="json"),
            "source_ids": [source.id for source in sources],
            "first_recommended_at": now(),
            "updated_at": now(),
            "run_id": run_id,
            "is_demo": True,
            "fingerprint": f"demo-{index}",
            "outcome": {"status": "unreviewed", "note": ""},
        }
        store.put("account", account_id, account)
        store.put("snapshot", run_id + ":" + account_id, account)
        ids.append(account_id)
    store.put(
        "run",
        run_id,
        {
            "id": run_id,
            "status": "completed",
            "stage": "Three synthetic accounts illustrate the review workflow.",
            "created_at": now(),
            "completed_at": now(),
            "is_demo": True,
            "profile": profile.model_dump(),
            "settings": Settings().model_dump(),
            "candidate_count": 3,
            "processed": 3,
            "account_ids": ids,
            "error": None,
            "input_review": {"observations": [], "hypotheses": []},
        },
    )
    return run_id
