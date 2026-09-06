# Research-layer threat model

Scope: one user on a trusted Mac, a local Docker engine, permitted public websites, untrusted search/page content and OpenRouter inference. This document records design reasoning, not a security certification. The trust boundaries are browser-to-local-app, app-to-gateway, gateway-to-MCP service, crawler-to-public-network and evidence-to-model.

| Threat | Implemented control | Residual risk |
| --- | --- | --- |
| Direct/indirect prompt injection and excessive agency | Source data uses explicit untrusted delimiters; fixed tool allowlist; no shell, email or CRM tool; output schemas and independent evidence gate | Models can still misinterpret evidence. Tests establish tool boundaries, not universal resistance to persuasion. |
| Malicious websites and SSRF | HTTP(S) only, standard ports, public DNS/IP validation, noncanonical numeric-IP rejection, DNS-pinned transport, redirect revalidation and robots checks | Application checks are not a replacement for an independently enforced network firewall. |
| Browser network abuse | All requests use guarded transport; closed proxy for unintercepted requests; no POST, downloads or WebSockets; finite bytes/time/request count; disposable browser | A browser/runtime compromise is outside the Python policy boundary. Container limits reduce impact but do not certify isolation. |
| MCP misuse, credential theft and insecure service access | Bearer authentication, separate service credentials/volumes, loopback-only published ports, no browser origins, restricted schemas | Static service tokens need manual rotation; a trusted local admin/Docker operator can read private data. |
| Unbounded crawling, resource exhaustion and denial of wallet | Persistent quotas, 20-page/depth-3 crawl maximum, timeouts, concurrency/rate limits, response bounds, existing $5 shared model ledger | Failed attempts may consume their reserved allowance. An authorised user can intentionally start more runs. |
| Poisoned data, compromised search and manipulated provenance | Search is a lead, fetched sources carry hashes and provenance, first-party status is explicit, facts/inferences/hypotheses remain distinct | Hashes detect accidental or inconsistent modification, not a malicious source or service that fabricates content and a matching hash. |
| Compromised MCP service or software dependency | Independently validate service outputs, enforce gateway URL policy, scoped token mounts, pinned SearXNG digest and locked Python dependencies | The containers share a Docker network; this is not a mutually untrusted multi-tenant service mesh. |
| Missing visibility and cascading failures | Typed errors, per-tool redacted audit records, model ledger, bounded search retries, circuit breaker, saved progress and partial evidence | Gateway aggregate metrics are process-local; no external alerting or distributed trace service is configured. |

## Taxonomy mapping

These are contextual mappings made for this implementation, not OWASP/CSA certification. The authoritative reference is the [OWASP GenAI Security Project crosswalk](https://genai-security-project.github.io/crosswalk/), with background in its [Agentic Top 10 announcement](https://genai.owasp.org/2025/12/09/owasp-top-10-for-agentic-applications-the-benchmark-for-agentic-security-in-the-age-of-autonomous-ai/).

- Goal-changing page instructions relate to ASI01; misuse of research tools relates to ASI02.
- Service identity/privilege boundaries relate to ASI03; dependency and MCP-service compromise relate to ASI04.
- Untrusted-content-to-code concerns relate to ASI05; poisoned stored context and evidence relate to ASI06.
- Service communication boundaries relate to ASI07; repeated dependent failures relate to ASI08.
- Over-trusting a confident account brief relates to ASI09. No autonomous multi-agent system is deployed, so an ASI10-specific claim is not made.

[CSA's MAESTRO framework](https://cloudsecurityalliance.org/blog/2025/02/06/agentic-ai-threat-modeling-framework-maestro) provides a complementary layered view. Here model interpretation concerns sit at the model layer; provenance/cache concerns at data operations; graph and MCP controls at agent frameworks; Docker/network/credential handling at deployment and infrastructure; audit/metrics at evaluation and observability. Source policy and human review are cross-cutting security controls. This is a practical scope mapping, not a claim to implement every MAESTRO control.

## Test boundary

Automated tests use synthetic prompts and a deterministic fixture site. They cover missing authentication, cross-origin MCP requests, malformed or excessive arguments, internal DNS answers, numeric-IP ambiguity, redirect revalidation, DNS pinning, oversized responses, cache isolation/expiry, evidence-hash checks, circuit breaking and a real Crawl4AI/MCP/LangGraph path. Injected page text asking for credentials, shell execution, CRM writes or evidence deletion remains data; the approved tool graph does not gain those capabilities. No exploit campaign or Ultra13 certification run is performed. A later assessment should be explicitly scoped to this deployment and its controlled fixtures.
