# Security Policy

## Reporting a vulnerability

BoilingBrain is a documentation/template project — it has no runtime, no network surface, and no data store. The realistic risk surface is limited to:

- Malicious instructions injected into bootstrap prompts, slash-commands, or `*.tpl` files that could mislead Claude Code into running unsafe shell commands.
- Supply-chain issues in CI workflows (`.github/workflows/`) that could leak secrets or push unauthorized changes.

If you find something in either category, please report it privately:

- Open a [private security advisory](https://github.com/tetra-plg/boiling-brain/security/advisories/new) on GitHub, **or**
- Email the maintainer at `peije45@gmail.com` with `[boiling-brain security]` in the subject.

Please do **not** open a public issue for security reports.

## What to expect

- Acknowledgement within **5 business days**.
- A first assessment (accept / reject / need more info) within **14 days**.
- If accepted, a fix or mitigation in the next minor release, with credit in the CHANGELOG unless you prefer to remain anonymous.

## Out of scope

- Issues in user vaults built from this template — those are private to each user.
- Vulnerabilities in upstream dependencies (Claude Code, GitHub Actions) — report those to the upstream project.
- Theoretical issues without a demonstrable impact path on this repository.
