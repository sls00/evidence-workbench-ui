# Security Policy

## Supported versions
This portfolio package tracks `main`. Security fixes land on `main` via PR.

## Reporting a vulnerability
Please **do not** open a public issue for security-sensitive reports.

Email the maintainer (`@sls00` on GitHub) with:
- Affected surface (API route, SPA, subprocess runner, report path handling)
- Reproduction steps / PoC (non-destructive preferred)
- Impact assessment

You should receive an acknowledgement within a few days when the maintainer is available.

## Non-goals
This is a **local-first** review instrument (not multi-tenant SaaS). Treat filesystem run roots and sibling engine checkouts as trusted developer machine state.
