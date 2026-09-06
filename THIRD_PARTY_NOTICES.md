# Third-party notices

Dependencies retain their own copyright and license terms. A license for this repository's original code does not replace those terms or grant rights to retrieved web content, imported customer material, model services or Docker Desktop.

This source repository references upstream packages and container images; it does not vendor their source trees. The complete dependency versions are recorded in `uv.lock`, `web/package-lock.json` and `docker-compose.yml`. Preserve the licenses and notices included in those packages when redistributing binaries, bundles or images.

## Crawl4AI

This product includes software developed by UncleCode (https://x.com/unclecode) as part of the Crawl4AI project (https://github.com/unclecode/crawl4ai).

The pinned Crawl4AI 0.9.3 [license](https://github.com/unclecode/crawl4ai/blob/v0.9.3/LICENSE) contains Apache 2.0 terms and an additional attribution requirement. Keep the attribution above in distributions and the application credits. Source: [Crawl4AI v0.9.3](https://github.com/unclecode/crawl4ai/tree/v0.9.3).

## SearXNG

SearXNG runs as a separate upstream container, accessed through its HTTP interface. The configured source revision is [c7f3080aac5de13b619c4a5ab36590a2c5165e1c](https://github.com/searxng/searxng/tree/c7f3080aac5de13b619c4a5ab36590a2c5165e1c); its [GNU AGPLv3 license](https://github.com/searxng/searxng/blob/c7f3080aac5de13b619c4a5ab36590a2c5165e1c/LICENSE) applies to SearXNG. This repository supplies deployment configuration and does not modify SearXNG's source code. Review its source-distribution requirements before modifying or redistributing that service.

## Other components

The application also uses LangGraph, FastAPI, the MCP Python SDK, Playwright/Chromium, React, React DOM, Lucide and their dependencies. Their licenses are supplied with the installed packages. React and React DOM use MIT terms; Lucide uses ISC terms and identifies portions originating in Feather under MIT. UI dependency notices are also shipped in the built application's `/third-party-notices.txt` file.

This overview identifies the main components and the additional Crawl4AI notice; it is not an exhaustive transitive-dependency license inventory. A release that distributes prebuilt images or other binaries should retain the full notices shipped by every included component.
