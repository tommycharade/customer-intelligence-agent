import asyncio
import hashlib
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langsmith import tracing_context

from .evidence import canonical_domain, qualifies, validate_assessment, validate_links
from .models import (
    Assessment,
    Candidates,
    ChatAnswer,
    InputReview,
    Profile,
    Settings,
    Source,
    Verification,
    now,
    uid,
)
from .providers import OpenRouter, ServiceError, Tavily
from .routing import StructuredOutputError
from .sources import PublicReader, SourceUnavailable
from .store import BudgetExceeded


class ResearchState(TypedDict, total=False):
    run_id: str
    candidates: list[dict]
    index: int
    source_ids: list[str]
    assessment: dict | None
    accepted: list[str]
    input_review: dict
    review: dict | None


class Research:
    def __init__(self, store, secrets, checkpointer):
        self.store, self.secrets, self.checkpointer = store, secrets, checkpointer
        self.model = OpenRouter(store, secrets)
        self.search = Tavily(store, secrets)
        self.tasks = {}
        graph = StateGraph(ResearchState)
        for name, node in [
            ("review_inputs", self.review_inputs),
            ("discover", self.discover),
            ("select_account", self.select_account),
            ("collect", self.collect),
            ("assess", self.assess),
            ("save_account", self.save_account),
            ("finish", self.finish),
        ]:
            graph.add_node(name, node)
        graph.add_edge(START, "review_inputs")
        graph.add_edge("review_inputs", "discover")
        graph.add_edge("discover", "select_account")
        graph.add_conditional_edges(
            "select_account",
            lambda state: (
                "finish"
                if state["index"] >= len(state["candidates"]) or len(state["accepted"]) >= 10
                else "collect"
            ),
        )
        graph.add_edge("collect", "assess")
        graph.add_edge("assess", "save_account")
        graph.add_edge("save_account", "select_account")
        graph.add_edge("finish", END)
        self.graph = graph.compile(checkpointer=checkpointer)

    def active(self):
        return any(not task.done() for task in self.tasks.values())

    def run(self, state):
        return self.store.get("run", state["run_id"])

    def start(self, run_id, resume=False):
        if self.active():
            raise ValueError("Another research run or chat is active. Wait for it to finish or cancel it.")
        self.store.patch("run", run_id, status="running", error=None)
        self.tasks[run_id] = asyncio.create_task(self.execute(run_id, resume))

    async def execute(self, run_id, resume):
        self.store.patch("run", run_id, status="running", error=None)
        config = {"configurable": {"thread_id": run_id}, "recursion_limit": 250}
        try:
            await self.model.prepare(self.store.get("run", run_id)["settings"])
            checkpoint = await self.graph.aget_state(config) if resume else None
            state = (
                None if checkpoint and checkpoint.values else {"run_id": run_id, "index": 0, "accepted": []}
            )
            with tracing_context(enabled=False):
                await self.graph.ainvoke(state, config=config, durability="sync")
        except asyncio.CancelledError:
            self.store.patch("run", run_id, status="cancelled", stage="Stopped; progress saved")
            self.store.event(run_id, "Stopped. Resume continues from the last completed step.")
        except (BudgetExceeded, ServiceError) as error:
            self.store.patch("run", run_id, status="paused", error=str(error), stage="Progress saved")
            self.store.event(run_id, str(error))
        except Exception:
            self.store.patch(
                "run",
                run_id,
                status="interrupted",
                error="A research step could not finish. Saved progress is intact; resume to retry.",
                stage="Progress saved",
            )
            self.store.event(
                run_id, "A step failed validation or could not complete. Resume retries the unfinished step."
            )

    def stage(self, state, message):
        self.store.patch("run", state["run_id"], stage=message)
        self.store.event(state["run_id"], message)

    def uploads(self, source_type=None):
        return [
            Source.model_validate(source)
            for source in self.store.all("source")
            if source["origin"] == "upload"
            and not source["is_demo"]
            and (source_type is None or source["source_type"] == source_type)
        ]

    async def cached_search(self, run_id, query):
        cache_id = run_id + ":" + hashlib.sha256(query.encode()).hexdigest()
        cached = self.store.get("search_cache", cache_id)
        if cached is not None:
            return cached["hits"]
        hits = await self.search.search(run_id, query)
        self.store.put("search_cache", cache_id, {"hits": hits})
        return hits

    async def review_inputs(self, state):
        self.stage(state, "Reviewing your enquiries and interview notes")
        inputs = [
            source for source in self.uploads() if source.source_type in {"inbound", "interview", "other"}
        ]
        review = {"observations": [], "hypotheses": []}
        if inputs:
            result = await self.model.structured(
                state["run_id"],
                InputReview,
                "Review the supplied notes for recurring workflow observations and hypotheses relevant to the profile. Label customer reports as reports. Never infer one company's problem from another company's notes. This is background context only, never public-search query text.",
                {
                    "profile": self.run(state)["profile"],
                    "inputs": [{"title": source.title, "text": source.text[:4000]} for source in inputs[:20]],
                    "prior_review_feedback": [
                        {"company": account["name"], "outcome": account["outcome"]}
                        for account in self.store.all("account")
                        if not account["is_demo"]
                    ][:30],
                },
                role="extraction",
            )
            review = result.model_dump()
        self.store.patch("run", state["run_id"], input_review=review)
        return {"input_review": review}

    async def discover(self, state):
        self.stage(state, "Finding accounts that match your profile")
        run = self.run(state)
        if run.get("target_domain"):
            domain = run["target_domain"]
            return {"candidates": [{"domain": domain, "name": domain, "urls": ["https://" + domain]}]}
        profile = Profile.model_validate(run["profile"])
        candidates = [
            {"name": source.title, "domain": source.account_domain, "urls": []}
            for source in self.uploads()
            if source.account_domain and source.source_type != "exclusion"
        ]
        # Queries are built solely from public profile criteria, never from imported text or model-generated notes.
        queries = [
            f"{profile.company_type} {profile.technology} {profile.geography}",
            f"{profile.company_type} {profile.technology} engineering documentation",
            f"{profile.company_type} {profile.technology} careers jobs",
        ]
        hits = []
        for query in queries:
            hits.extend(await self.cached_search(state["run_id"], query))
        if hits:
            found = await self.model.structured(
                state["run_id"],
                Candidates,
                "Extract candidate COMPANY accounts from these search leads. Identify canonical company domains. Exclude job boards, publishers, consultancies excluded by the profile, generic forums, vendor directories and aggregators as candidate companies. URLs must be copied exactly from supplied search hits. These snippets are discovery leads, not evidence. Return at most 30 plausible companies; an empty list is valid.",
                {"profile": run["profile"], "search_leads": hits},
                role="extraction",
            )
            known_urls = {hit["url"] for hit in hits}
            for account in found.accounts:
                item = account.model_dump()
                item["urls"] = [url for url in item["urls"] if url in known_urls]
                candidates.append(item)
        excluded = {source.account_domain for source in self.uploads("exclusion")}
        existing = {
            account["domain"]: account for account in self.store.all("account") if not account["is_demo"]
        }
        unique = {}
        for candidate in candidates:
            try:
                domain = canonical_domain(candidate["domain"])
            except ValueError:
                continue
            prior = existing.get(domain)
            if domain in excluded or (
                prior
                and prior["outcome"]["status"]
                in {"rejected", "contacted", "conversation", "relevant_conversation"}
            ):
                continue
            unique.setdefault(domain, candidate | {"domain": domain})
        result = list(unique.values())[: run["settings"]["candidate_limit"]]
        self.store.patch("run", state["run_id"], candidate_count=len(result))
        return {"candidates": result}

    async def select_account(self, state):
        return {}

    async def collect(self, state):
        candidate = state["candidates"][state["index"]]
        domain = candidate["domain"]
        self.stage(state, f"Reading sources for {candidate['name']}")
        run = self.run(state)
        reader = PublicReader(Settings.model_validate(run["settings"]))
        source_ids = [
            source.id
            for source in self.uploads()
            if source.account_domain == domain and source.source_type not in {"asset", "exclusion"}
        ]
        urls = ["https://" + domain] + candidate.get("urls", [])[:1]
        for query in [
            f"site:{domain} {run['profile']['technology']} documentation engineering",
            f"site:{domain} careers news {run['profile']['buying_trigger']}",
            f'"{domain}" {run["profile"]["technology"]} technical discussion',
        ]:
            hits = await self.cached_search(state["run_id"], query)
            # Reserve room for documentation, timing and discussion evidence rather than
            # allowing the first group of search results to consume the source allowance.
            urls.extend(hit["url"] for hit in hits[:2])
        for url in list(dict.fromkeys(urls))[:8]:
            # Persist each successful fetch immediately; resuming a failed collect step reuses it.
            cache_id = state["run_id"] + ":" + hashlib.sha256(url.encode()).hexdigest()
            cached = self.store.get("fetch_cache", cache_id)
            if cached and self.store.get("source", cached["source_id"]):
                source_ids.append(cached["source_id"])
                continue
            try:
                source = await reader.read(url, domain)
                source.id = hashlib.sha256(
                    (state["run_id"] + str(source.url) + source.content_hash).encode()
                ).hexdigest()[:32]
                if not self.store.get("source", source.id):
                    self.store.put("source", source.id, source)
                self.store.put("fetch_cache", cache_id, {"source_id": source.id})
                source_ids.append(source.id)
            except SourceUnavailable as error:
                self.store.event(state["run_id"], f"Source unavailable for {domain}: {error}", url=url)
        return {"source_ids": list(dict.fromkeys(source_ids)), "assessment": None, "review": None}

    def review_record(self, run_id, verification):
        call = self.store.get("model_call", verification._call_id) if verification._call_id else None
        config = Settings.model_validate(self.store.get("run", run_id)["settings"]).models.review
        return {
            "call_id": verification._call_id,
            "model": config.model,
            "reasoning_effort": config.reasoning_effort,
            "provider": call.get("provider") if call else None,
            "at": now(),
            **verification.model_dump(),
        }

    async def assess(self, state):
        candidate = state["candidates"][state["index"]]
        if candidate["domain"] in {source.account_domain for source in self.uploads("exclusion")}:
            self.store.event(
                state["run_id"], f"{candidate['domain']}: excluded by your imported account list."
            )
            return {"assessment": None}
        self.stage(state, f"Checking fit and evidence for {candidate['name']}")
        sources = [
            Source.model_validate(source)
            for id in state["source_ids"]
            if (source := self.store.get("source", id))
        ]
        if not sources:
            self.store.event(state["run_id"], f"{candidate['domain']}: no readable account evidence found.")
            return {"assessment": None}
        run = self.run(state)
        assets = self.uploads("asset")
        data = {
            "today": now()[:10],
            "target": candidate,
            "profile": run["profile"],
            "background_only": state.get("input_review", {}),
            "sources": [source.model_dump(mode="json") | {"text": source.text[:10000]} for source in sources],
            "assets": [
                {"id": asset.id, "title": asset.title, "text": asset.text[:2000]} for asset in assets[:20]
            ],
        }
        instruction = """Write a short account brief. Assess exactly company_type, technology and workflow criteria with direct evidence. Do not mistake vendor documentation for evidence that a customer uses that vendor. Apply all profile exclusions. Use fit=unknown or weak when evidence is inadequate. Each claim references a supplied source ID and an EXACT continuous quote. Hiring engineers does not establish architecture drift. Include exactly user, champion and budget_holder roles, usually as explicitly uncertain hypotheses; name people only when an excerpt supports their name AND role. why_now is null unless a fact has a genuinely evidenced event date within the profile's trigger_days; retrieval dates are not event dates. Never fabricate a date. Prefer useful conversations when no matching asset exists; mark unbuilt assets proposed_asset. Missing data is preferable to unsupported claims."""
        for attempt in range(2):
            verification = None
            try:
                assessment = await self.model.structured(
                    state["run_id"], Assessment, instruction, data, role="research"
                )
                issues = validate_assessment(
                    assessment, sources, assets, Profile.model_validate(run["profile"]), candidate["domain"]
                )
                if not issues:
                    self.stage(state, f"Reviewing evidence for {candidate['name']}")
                    verification = await self.model.structured(
                        state["run_id"],
                        Verification,
                        "Independently audit this brief against ONLY the provided account sources. Fail if any factual claim, criterion support, date, named person's role or claimed absence contradicts or goes beyond its quote and surrounding context. Check company identity and profile exclusions carefully. A quote existing does not mean it entails a claim. Check event dates against the source text; retrieval timestamps are not events. Hypotheses must be plausible, explicitly labelled and distinguish the observation from its inference. Do not punish missing timing or role-only stakeholders. Return supported=false with concrete issues when uncertain about a factual assertion.",
                        {
                            "brief": assessment.model_dump(mode="json"),
                            "sources": [source.model_dump(mode="json") for source in sources],
                            "profile": run["profile"],
                        },
                        role="review",
                    )
                    issues = (
                        []
                        if verification.supported
                        else (
                            verification.issues
                            or ["The independent evidence check could not support the brief."]
                        )
                    )
            except StructuredOutputError as error:
                issues = [str(error)]
            if not issues and verification is not None:
                return {
                    "assessment": assessment.model_dump(mode="json"),
                    "review": self.review_record(state["run_id"], verification),
                }
            data["corrections_required"] = issues
            if attempt == 0:
                self.store.event(state["run_id"], f"Checking corrections for {candidate['domain']}.")
        self.store.event(
            state["run_id"],
            f"{candidate['domain']}: withheld because its brief did not pass evidence checks.",
        )
        return {"assessment": None}

    async def save_account(self, state):
        # Older checkpoints can arrive here without a recorded verdict. Review them
        # with their original model settings before allowing a recommendation.
        if state.get("assessment") and not (state.get("review") or {}).get("supported"):
            state = {**state, **await self.assess(state)}
        accepted = list(state["accepted"])
        if state["assessment"]:
            brief = Assessment.model_validate(state["assessment"])
            if qualifies(brief):
                domain = canonical_domain(brief.domain)
                account_id = hashlib.sha256(domain.encode()).hexdigest()[:24]
                previous = self.store.get("account", account_id)
                hashes = sorted(
                    self.store.get("source", source_id)["content_hash"] for source_id in state["source_ids"]
                )
                fingerprint = hashlib.sha256("".join(hashes).encode()).hexdigest()
                if (
                    not previous
                    or previous.get("fingerprint") != fingerprint
                    or previous.get("run_id") == state["run_id"]
                    or self.run(state).get("target_domain")
                ):
                    account = {
                        "id": account_id,
                        "domain": domain,
                        "name": brief.company_name,
                        "brief": brief.model_dump(mode="json"),
                        "review": state["review"],
                        "source_ids": state["source_ids"],
                        "first_recommended_at": previous["first_recommended_at"] if previous else now(),
                        "updated_at": now(),
                        "run_id": state["run_id"],
                        "is_demo": False,
                        "fingerprint": fingerprint,
                        "outcome": previous["outcome"] if previous else {"status": "unreviewed", "note": ""},
                    }
                    self.store.put("account", account_id, account)
                    self.store.put("snapshot", state["run_id"] + ":" + account_id, account)
                    if account_id not in accepted:
                        accepted.append(account_id)
                    self.store.event(
                        state["run_id"], f"Saved evidence-backed brief for {brief.company_name}."
                    )
                else:
                    self.store.event(
                        state["run_id"],
                        f"{brief.company_name}: unchanged evidence; previous recommendation retained.",
                    )
            else:
                self.store.event(
                    state["run_id"],
                    f"{brief.company_name}: not recommended ({', '.join(brief.matched_exclusions) or 'insufficient demonstrated fit'}).",
                )
        self.store.patch("run", state["run_id"], processed=state["index"] + 1, account_ids=accepted)
        return {
            "index": state["index"] + 1,
            "accepted": accepted,
            "assessment": None,
            "source_ids": [],
            "review": None,
        }

    async def finish(self, state):
        count = len(state["accepted"])
        message = f"{count} account{'s' if count != 1 else ''} recommended."
        if count < 10:
            message += " The remaining candidates did not provide enough new, qualifying evidence."
        self.store.patch(
            "run",
            state["run_id"],
            status="completed",
            stage=message,
            completed_at=now(),
            account_ids=state["accepted"],
        )
        self.store.event(state["run_id"], message)
        return {}

    async def chat(self, account, message):
        sources = [
            Source.model_validate(source)
            for id in account["source_ids"]
            if (source := self.store.get("source", id))
        ]
        if account["is_demo"]:
            answer = ChatAnswer(
                answer="This is a synthetic demonstration. The brief illustrates how direct observations support an account recommendation while stakeholder roles and possible problems remain hypotheses. Connect your API keys and run live research to ask questions about real accounts.",
                evidence=[],
            )
        else:
            await self.model.prepare(self.store.get("run", account["run_id"])["settings"])
            data = {
                "question": message,
                "brief": account["brief"],
                "sources": [source.model_dump() | {"text": source.text[:10000]} for source in sources],
            }
            for attempt in range(2):
                try:
                    answer = await self.model.structured(
                        account["run_id"],
                        ChatAnswer,
                        "Answer this question about the selected account using only its saved brief and sources. Attach exact quotes for factual assertions. Be explicit when the sources do not answer the question. This chat does not perform new web research; explain that Refresh research starts a new run when fresh evidence is needed.",
                        data,
                        role="research",
                    )
                    issues = validate_links(answer.evidence, {source.id: source for source in sources})
                    if not issues:
                        verification = await self.model.structured(
                            account["run_id"],
                            Verification,
                            "Audit this contextual answer against the supplied source text. Every factual assertion must be supported, with citations attached. Hypotheses and uncertainty must remain explicit. Unsupported questions can be answered by acknowledging missing evidence. Reject invented facts, names, events or unsupported conclusions even if an exact quote exists elsewhere in the answer.",
                            {
                                "answer": answer.model_dump(),
                                "sources": [source.model_dump(mode="json") for source in sources],
                            },
                            role="review",
                        )
                        issues = (
                            []
                            if verification.supported
                            else (verification.issues or ["The answer is unsupported."])
                        )
                except StructuredOutputError as error:
                    issues = [str(error)]
                if not issues:
                    break
                data["corrections_required"] = issues
            else:
                raise ServiceError(
                    "The answer could not be supported by the saved evidence after one repair. Try a more specific question or refresh research."
                )
        record = {
            "id": uid(),
            "account_id": account["id"],
            "at": now(),
            "question": message,
            **answer.model_dump(),
            "review": None if account["is_demo"] else self.review_record(account["run_id"], verification),
        }
        self.store.put("chat", record["id"], record)
        return record
