from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")
    _call_id: str | None = PrivateAttr(default=None)


class Profile(Model):
    offering: str = Field(min_length=3, max_length=3000)
    company_type: str = Field(min_length=3, max_length=1000)
    technology: str = Field(min_length=2, max_length=1000)
    buyer_role: str = Field(min_length=2, max_length=1000)
    problem: str = Field(min_length=3, max_length=2000)
    buying_trigger: str = Field(min_length=3, max_length=1500)
    exclusions: list[str] = Field(min_length=1, max_length=30)
    geography: str = Field(default="", max_length=500)
    trigger_days: int = Field(default=90, ge=1, le=730)

    @field_validator("offering", "company_type", "technology", "buyer_role", "problem", "buying_trigger")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Enter a specific value")
        return value.strip()

    @field_validator("exclusions")
    @classmethod
    def nonblank_exclusions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("Exclusions cannot be blank")
        return [value.strip() for value in values]


SourceType = Literal[
    "website", "documentation", "job", "discussion", "inbound", "interview", "asset", "exclusion", "other"
]


class Source(Model):
    id: str = Field(default_factory=uid)
    title: str
    text: str
    source_type: SourceType = "other"
    origin: Literal["public", "upload", "demo"] = "upload"
    url: str | None = None
    account_domain: str | None = None
    published_at: str | None = None
    retrieved_at: str = Field(default_factory=now)
    content_hash: str = ""
    is_demo: bool = False
    provenance: dict = Field(default_factory=dict)


class Evidence(Model):
    source_id: str
    quote: str = Field(min_length=12, max_length=1800)


class Claim(Model):
    text: str = Field(min_length=3, max_length=1800)
    kind: Literal["fact", "inference", "hypothesis"]
    evidence: list[Evidence] = Field(min_length=1, max_length=5)
    reasoning: str | None = None
    event_date: date | None = None


class Stakeholder(Model):
    role: Literal["user", "champion", "budget_holder"]
    title: str
    name: str | None = None
    confidence: Literal["low", "medium", "high"]
    basis: Claim


class HelpfulAction(Model):
    kind: Literal["asset", "conversation", "proposed_asset"]
    title: str
    reason: str
    asset_id: str | None = None


class Criterion(Model):
    criterion: Literal["company_type", "technology", "workflow"]
    status: Literal["supported", "unsupported", "unknown"]
    evidence: list[Evidence]


class Assessment(Model):
    company_name: str
    domain: str
    summary: str = Field(max_length=500)
    fit: Literal["strong", "plausible", "weak", "excluded", "unknown"]
    criteria: list[Criterion]
    matched_exclusions: list[str]
    why_fits: list[Claim] = Field(min_length=1, max_length=5)
    why_now: Claim | None
    who_matters: list[Stakeholder]
    what_could_help: list[HelpfulAction] = Field(min_length=1, max_length=3)


class Verification(Model):
    supported: bool
    issues: list[str]


class Candidate(Model):
    name: str
    domain: str
    urls: list[str] = Field(default_factory=list)


class Candidates(Model):
    accounts: list[Candidate] = Field(max_length=40)


class InputReview(Model):
    observations: list[str]
    hypotheses: list[str]


ModelRole = Literal["extraction", "research", "review"]
ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
MODEL_ROLES = ("extraction", "research", "review")
OUTPUT_LIMITS = {"extraction": 4096, "research": 8192, "review": 16384}


class RoleModel(Model):
    model: str = Field(min_length=1, max_length=200)
    reasoning_effort: ReasoningEffort | None = None

    @field_validator("model")
    @classmethod
    def model_id(cls, value):
        if not value.strip() or any(character.isspace() for character in value):
            raise ValueError("Enter a model ID without whitespace")
        return value


class TaskModels(Model):
    extraction: RoleModel = Field(
        default_factory=lambda: RoleModel(model="z-ai/glm-5.3-flash", reasoning_effort="low")
    )
    research: RoleModel = Field(
        default_factory=lambda: RoleModel(model="z-ai/glm-5.3-flash", reasoning_effort="low")
    )
    review: RoleModel = Field(
        default_factory=lambda: RoleModel(model="z-ai/glm-5.3", reasoning_effort="high")
    )


class Settings(Model):
    models: TaskModels = Field(default_factory=TaskModels)
    model_budget: float = Field(default=5, ge=0.10, le=100)
    max_search_queries: int = Field(default=60, ge=1, le=100)
    max_pages_fetched: int = Field(default=80, ge=1, le=120)
    max_search_iterations: int = Field(default=3, ge=1, le=3)
    max_llm_iterations: int = Field(default=5, ge=5, le=12)
    candidate_limit: int = Field(default=40, ge=1, le=40)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    browser_fallback: bool = True

    @model_validator(mode="before")
    @classmethod
    def legacy_model(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            legacy_budget = value.pop("search_budget", None)
            if legacy_budget is not None:
                value.setdefault("max_search_queries", min(100, max(1, legacy_budget)))
        if isinstance(value, dict) and "model" in value:
            legacy = value.pop("model")
            if "models" in value:
                raise ValueError("Supply task models or a legacy model, not both")
            value["models"] = {role: {"model": legacy, "reasoning_effort": None} for role in MODEL_ROLES}
        return value


class Outcome(Model):
    status: Literal[
        "unreviewed", "shortlisted", "rejected", "contacted", "conversation", "relevant_conversation"
    ]
    note: str = Field(default="", max_length=5000)

    @field_validator("note")
    @classmethod
    def rejection_reason(cls, value, info):
        if info.data.get("status") == "rejected" and not value.strip():
            raise ValueError("Record why this account was rejected.")
        return value


class ChatRequest(Model):
    message: str = Field(min_length=1, max_length=3000)


class ChatAnswer(Model):
    answer: str
    evidence: list[Evidence]


class ResearchGaps(Model):
    sufficient: bool
    gaps: list[Literal["company_type", "technology", "workflow", "timing"]] = Field(max_length=4)
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=1000)
