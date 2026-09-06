from typing import Literal
from urllib.parse import unquote, urlparse, urlunparse

from pydantic import Field, field_validator

from ..evidence import canonical_domain
from ..models import Model, now, uid


class ToolContext(Model):
    request_id: str = Field(default_factory=uid, pattern=r"^[\w:-]{1,120}$")
    graph_run_id: str = Field(pattern=r"^[\w:-]{1,120}$")
    allowed_domains: list[str] = Field(default_factory=list, max_length=100)
    blocked_domains: list[str] = Field(default_factory=list, max_length=100)
    max_search_queries: int = Field(default=60, ge=1, le=100)
    max_pages_fetched: int = Field(default=80, ge=1, le=120)
    browser_fallback: bool = True

    @field_validator("allowed_domains", "blocked_domains")
    @classmethod
    def domains(cls, values):
        return [canonical_domain(value) for value in values]


class SearchArgs(Model):
    query: str = Field(min_length=2, max_length=1200)
    max_results: int = Field(default=10, ge=1, le=20)
    language: str = Field(default="en", pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    time_range: Literal["day", "week", "month", "year"] | None = None


class PageArgs(Model):
    url: str = Field(max_length=2048)
    account_domain: str | None = None

    @field_validator("url")
    @classmethod
    def public_url(cls, value):
        return normalize_url(value)

    @field_validator("account_domain")
    @classmethod
    def domain(cls, value):
        return canonical_domain(value) if value else None


class CrawlArgs(PageArgs):
    max_pages: int = Field(default=8, ge=1, le=20)
    max_depth: int = Field(default=1, ge=0, le=3)
    allowed_paths: list[str] = Field(
        default_factory=lambda: ["/about", "/product", "/docs", "/blog", "/careers", "/security"],
        max_length=20,
    )

    @field_validator("allowed_paths")
    @classmethod
    def paths(cls, values):
        if any(
            not value.startswith("/")
            or value.startswith("//")
            or ".." in unquote(value)
            or "?" in value
            or len(value) > 200
            for value in values
        ):
            raise ValueError("Use bounded, absolute path prefixes without query strings or traversal.")
        return values


class ExtractArgs(PageArgs):
    fields: dict[str, str] = Field(min_length=1, max_length=20)

    @field_validator("fields")
    @classmethod
    def selectors(cls, values):
        import re

        for name, selector in values.items():
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_]{0,49}", name) or not re.fullmatch(
                r"[a-zA-Z0-9_.# >-]{1,120}", selector
            ):
                raise ValueError("Use simple CSS tag, class or ID selectors and named text fields.")
        return values


class SearchHit(Model):
    title: str = Field(max_length=1000)
    url: str = Field(max_length=2048)
    snippet: str = Field(max_length=4000)
    source: str = Field(default="SearXNG", max_length=200)
    retrieved_at: str = Field(default_factory=now)
    rank: int = Field(ge=1, le=100)
    search_query: str = Field(max_length=1200)
    request_id: str
    untrusted: Literal[True] = True


class WebEvidence(Model):
    evidence_id: str = Field(default_factory=uid)
    account_domain: str | None = None
    source_url: str
    source_domain: str
    title: str = Field(max_length=1000)
    retrieved_at: str = Field(default_factory=now)
    published_at: str | None = None
    content: str = Field(max_length=60000)
    content_hash: str
    extraction_method: str = "crawl4ai"
    search_query: str | None = None
    search_rank: int | None = None
    claim_type: Literal["observation"] = "observation"
    trust_level: Literal["first_party", "reputable_third_party", "unknown"] = "unknown"
    request_id: str
    links: list[str] = Field(default_factory=list, max_length=100)
    untrusted: Literal[True] = True


class Finding(Model):
    finding_id: str = Field(default_factory=uid)
    account_id: str
    statement: str
    classification: Literal["observed_fact", "supported_inference", "hypothesis"]
    evidence_ids: list[str] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)
    created_at: str = Field(default_factory=now)


def normalize_url(value):
    if any(ord(char) < 33 for char in value) or "\\" in value:
        raise ValueError("Malformed URL.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only credential-free HTTP and HTTPS URLs are permitted.")
    if parsed.port not in {None, 80, 443}:
        raise ValueError("Only standard public web ports are permitted.")
    host = parsed.hostname.lower().rstrip(".")
    if "%" in host or host.endswith((".localhost", ".local", ".internal")) or host == "localhost":
        raise ValueError("Internal or encoded hostnames are not permitted.")
    # Canonicalise IDNA and discard fragments; DNS/IP policy is checked separately on every fetch.
    host = host.encode("idna").decode()
    netloc = f"[{host}]" if ":" in host else host
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc, fragment=""))
