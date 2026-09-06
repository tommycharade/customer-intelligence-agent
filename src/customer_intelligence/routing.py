"""Endpoint-aware model compatibility and conservative token-price bounds."""

import asyncio
import math
import time

import httpx

from .models import MODEL_ROLES, OUTPUT_LIMITS, RoleModel, Settings, now

EFFORTS = ["max", "xhigh", "high", "medium", "low", "minimal", "none"]


class ServiceError(Exception):
    pass


class StructuredOutputError(ServiceError):
    pass


def reasoning_options(item):
    reasoning = item.get("reasoning") or {}
    values = reasoning.get("supported_efforts", [])
    values = EFFORTS if values is None else values
    return [
        value for value in values if value in EFFORTS and not (value == "none" and reasoning.get("mandatory"))
    ]


def price_bounds(pricing, input_bound=0):
    """Include every reachable context tier and any cache-write/reasoning premium."""
    tiers = [pricing]
    for override in pricing.get("overrides", []):
        if int(override.get("min_prompt_tokens", 0)) <= input_bound:
            tiers.append(pricing | override)
    rates = []
    for tier in tiers:
        prompt, completion = float(tier["prompt"]), float(tier["completion"])
        values = [prompt, completion, float(tier.get("request", 0))]
        cache_write = float(tier.get("input_cache_write", 0))
        internal_reasoning = float(tier.get("internal_reasoning", 0))
        if not all(
            math.isfinite(value) and value >= 0 for value in values + [cache_write, internal_reasoning]
        ):
            raise ValueError("Unavailable token pricing")
        if values[2]:
            raise ValueError("Per-request pricing is not supported")
        rates.append((prompt, completion, max(prompt, cache_write), max(completion, internal_reasoning)))
    return tuple(max(rate[index] for rate in rates) for index in range(4))


class ModelCatalogue:
    def __init__(self):
        self.items = {}
        self.endpoints = {}
        self.fetched_at = None
        self.loaded_at = 0
        self.lock = asyncio.Lock()

    async def refresh(self, force=False):
        async with self.lock:
            if not force and self.fetched_at and time.monotonic() - self.loaded_at < 300:
                return
            try:
                async with httpx.AsyncClient(timeout=30, trust_env=False) as client:
                    models, zdr = await asyncio.gather(
                        client.get("https://openrouter.ai/api/v1/models"),
                        client.get("https://openrouter.ai/api/v1/endpoints/zdr"),
                    )
                models.raise_for_status()
                zdr.raise_for_status()
                items = {item["id"]: item for item in models.json()["data"]}
                endpoints = {}
                for endpoint in zdr.json()["data"]:
                    endpoints.setdefault(endpoint["model_id"], []).append(endpoint)
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
                raise ServiceError(
                    "Could not refresh OpenRouter models, prices and ZDR endpoints. Check your connection and retry."
                ) from error
            self.items, self.endpoints = items, endpoints
            self.fetched_at, self.loaded_at = now(), time.monotonic()

    def eligible(self, model, role, effort=None, input_bound=0):
        item = self.items.get(model)
        if not item:
            return [], "This model is not in the current OpenRouter catalogue."
        if effort is not None and effort not in reasoning_options(item):
            return [], "This model does not support the selected reasoning effort."
        endpoints = self.endpoints.get(model, [])
        if not endpoints:
            return [], "No zero-data-retention endpoint is available."
        valid = []
        for endpoint in endpoints:
            parameters = endpoint.get("supported_parameters", [])
            if endpoint.get("status", 0) != 0 or not endpoint.get("tag"):
                continue
            if "max_tokens" not in parameters or "response_format" not in parameters:
                continue
            if role != "extraction" and "structured_outputs" not in parameters:
                continue
            if effort is not None and "reasoning" not in parameters:
                continue
            limit = endpoint.get("max_completion_tokens")
            if limit is not None and limit < OUTPUT_LIMITS[role]:
                continue
            if (endpoint.get("context_length") or 0) < input_bound + OUTPUT_LIMITS[role]:
                continue
            if endpoint.get("max_prompt_tokens") is not None and endpoint["max_prompt_tokens"] < input_bound:
                continue
            try:
                price_bounds(endpoint["pricing"], input_bound)
            except (ValueError, KeyError, TypeError, OverflowError):
                continue
            valid.append(endpoint)
        return (
            valid,
            None
            if valid
            else "No available ZDR endpoint supports this task’s output format, token limits, reasoning and pricing requirements.",
        )

    def validate(self, settings):
        settings = Settings.model_validate(settings)
        for role in MODEL_ROLES:
            config = getattr(settings.models, role)
            _, reason = self.eligible(config.model, role, config.reasoning_effort)
            if reason:
                raise ServiceError(f"{role.title()} model {config.model}: {reason}")

    def route(self, config: RoleModel, role, input_bound):
        endpoints, reason = self.eligible(config.model, role, config.reasoning_effort, input_bound)
        if reason:
            raise ServiceError(f"{role.title()} model {config.model}: {reason}")
        priced = [(endpoint, price_bounds(endpoint["pricing"], input_bound)) for endpoint in endpoints]
        selected, rates = min(
            priced, key=lambda pair: input_bound * pair[1][2] + OUTPUT_LIMITS[role] * pair[1][3]
        )
        structured = "structured_outputs" in selected["supported_parameters"]
        # Every allowed fallback fits the same reserved envelope and response format.
        allowed = [
            endpoint["tag"]
            for endpoint, candidate in priced
            if all(candidate[index] <= rates[index] for index in range(4))
            and (not structured or "structured_outputs" in endpoint["supported_parameters"])
        ]
        return {
            "endpoints": allowed,
            "structured": structured,
            "rates": rates,
            "reservation": input_bound * rates[2] + OUTPUT_LIMITS[role] * rates[3],
            "pricing_checked_at": self.fetched_at,
        }

    def view(self):
        models = []
        for item in sorted(self.items.values(), key=lambda value: value["name"].lower()):
            roles = {}
            for role in MODEL_ROLES:
                endpoints, reason = self.eligible(item["id"], role)
                priced = sorted(endpoints, key=lambda endpoint: sum(price_bounds(endpoint["pricing"])[:2]))
                roles[role] = {
                    "compatible": bool(endpoints),
                    "reason": reason,
                    "endpoint_count": len(endpoints),
                    "supported_efforts": [
                        effort
                        for effort in reasoning_options(item)
                        if self.eligible(item["id"], role, effort)[0]
                    ],
                    "prices": [
                        {
                            "provider": endpoint["provider_name"],
                            "tag": endpoint["tag"],
                            "pricing": endpoint["pricing"],
                            "supported_efforts": reasoning_options(item)
                            if "reasoning" in endpoint["supported_parameters"]
                            else [],
                            "structured_outputs": "structured_outputs" in endpoint["supported_parameters"],
                        }
                        for endpoint in priced
                    ],
                }
            models.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "roles": roles,
                    "reasoning": {
                        "supported_efforts": reasoning_options(item),
                        "mandatory": bool((item.get("reasoning") or {}).get("mandatory")),
                        "default_effort": (item.get("reasoning") or {}).get("default_effort"),
                    },
                }
            )
        return {"models": models, "fetched_at": self.fetched_at}
