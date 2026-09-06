# Security policy

## Supported scope

Security fixes target the latest code on the default branch. Earlier snapshots have no separate maintenance schedule. This project is an early release for one user on a trusted local machine, with application and gateway ports published only on loopback. It has not received an independent security assessment.

The [threat model](docs/threat-model.md) describes implemented controls and their limits. The application has no remote-user authentication or tenant isolation suitable for a public or shared deployment. OpenRouter inference and public search still send selected information off the local machine; see the README's data and access section.

## Report privately

Use **Report a vulnerability** in this repository's [Security tab](https://github.com/tommycharade/customer-intelligence-agent/security) when available. If private reporting is unavailable, open an issue titled **Private security contact requested**, with no vulnerability details or sensitive data, so the maintainer can arrange a private channel.

Include the affected commit/version, the component and configuration involved, a description of the impact, and relevant sanitized evidence from an environment you control. Do not include real API keys, private launch links, MCP credentials, customer notes or exports. Do not test unrelated services or other people's deployments as part of a report.

Reports are handled on a best-effort basis; there is no guaranteed response time or bug bounty. Coordinate public disclosure with the maintainer so a fix and advisory can be prepared.
