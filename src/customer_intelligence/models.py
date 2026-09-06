from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def uid() -> str:
    return uuid4().hex


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


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


class Evidence(Model):
    source_id: str
    quote: str = Field(min_length=12, max_length=1800)


class Claim(Model):
    text: str = Field(min_length=3, max_length=1800)
    kind: Literal["fact", "hypothesis"]
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


class Settings(Model):
    model: str = "anthropic/claude-sonnet-4.6"
    model_budget: float = Field(default=5, ge=0.10, le=100)
    search_budget: int = Field(default=100, ge=1, le=1000)
    candidate_limit: int = Field(default=40, ge=1, le=40)
    allowed_domains: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    browser_fallback: bool = True


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
