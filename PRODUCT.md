# Customer Intelligence Agent

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Approved: React/TypeScript local web app, FastAPI/Python, LangGraph, OpenRouter, SQLite. Runs on one user's Mac.

## Users
Tom reviews a small prospect shortlist and decides which accounts deserve a useful conversation.

## Product Purpose
Explain why an account belongs in the pipeline, using inspectable evidence and explicit uncertainty.

## Capabilities and Constraints
One editable customer profile; selected uploads and pasted notes; on-demand runs; ten recommendations maximum; $5 OpenRouter budget per run; separate search budget; no outbound messaging. Show facts separately from hypotheses. Store private data outside Git. Track relevant conversations, not database size.

## Operating Context
Desktop browser, a local Mac service, external OpenRouter inference and self-hosted SearXNG/Crawl4AI research through authenticated MCP. Docker Compose runs the research services; the existing Mac UI and a separate optional Docker UI are supported. Initial customer profile and API keys are entered during setup. Synthetic demo material is clearly labelled.

## Product Principles
- Evidence is part of each recommendation.
- Weak evidence produces a smaller shortlist.
- Unknown timing and stakeholder identities stay unknown.
- The next helpful action is more useful than collecting contact details.
- Conversation outcomes guide evaluation.

## Brand Commitments
Approved implementation direction: restrained and readable account-review workspace, ranked shortlist beside the brief, contextual chat, and source excerpts alongside claims.

## Accessibility & Inclusion
Keyboard-operable controls, visible focus, readable contrast, reduced motion, responsive layouts.
