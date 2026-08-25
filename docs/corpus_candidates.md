# Public Corpus Candidate Inventory

Generated: 2026-08-19

Scope searched:

- `/home/rahul_shiv_shankar/Dev/Projects`
- `/home/rahul_shiv_shankar/Documents` - not present in this environment
- `/home/rahul_shiv_shankar/Downloads` - not present in this environment
- current repo: `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo`
- sibling sparse worktree: `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory`

Exclusions applied during discovery:

- `.venv`
- `node_modules`
- `__pycache__`
- `.git`
- `.cache`
- `models`
- `notes/daily`

Hard boundary: this is an import queue only. No candidate below has been imported into `public_corpus/` by this inventory.

## Summary

- Markdown files discovered: 41
- Already in `public_corpus/`: 10
- Recommended for public import after approval: 6
- Needs Rahul review before any import: 25
- Ignored as already-public corpus material: 10
- Ignored private daily captures: 0 discovered after exclusion

## Recommended Import Plan

Recommended batch for Rahul approval:

1. Summarize `/home/rahul_shiv_shankar/Dev/Projects/ABM Agent/abm-system/agents/voice_rules.md` into `public_corpus/case_studies/abm-system-voice-rules.md`.
2. Summarize `/home/rahul_shiv_shankar/Dev/Projects/AI Agent for Jobs/web-ui/SECURITY.md` into `public_corpus/case_studies/ai-agent-for-jobs-security.md`.
3. Summarize `/home/rahul_shiv_shankar/Dev/Projects/abm-frontend/AGENTS.md` into `public_corpus/case_studies/abm-frontend-architecture.md`.
4. Summarize `/home/rahul_shiv_shankar/Dev/Projects/hermes-buildathon/AGENTS.md` into `public_corpus/case_studies/hermes-buildathon-architecture.md`.
5. Summarize `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/api/README.md` into `public_corpus/projects/sparse-model-theory-api.md`.
6. Summarize `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/api/README.md` into `public_corpus/projects/sparse-model-theory-api.md` or merge into the existing Sparse Model Theory public file after showing a diff.

Do not import these as raw copies. Even apparently safe engineering docs should become recruiter/founder-facing case studies with source path, public-safe summary, evidence bullets, caveats, what the work proves, and suggested Ask Rahul queries.

## Proposed Public Corpus Structure

Current files already exist:

- `public_corpus/profile.md`
- `public_corpus/proof-of-work.md`
- `public_corpus/role-fit.md`
- `public_corpus/caveats.md`
- `public_corpus/projects/akshar.md`
- `public_corpus/projects/openclaw-demo.md`
- `public_corpus/projects/sahayak.md`
- `public_corpus/projects/second-brain-console.md`
- `public_corpus/projects/sparse-model-theory.md`

Proposed additions after approval:

- `public_corpus/resume.md`
- `public_corpus/case_studies/abm-system-voice-rules.md`
- `public_corpus/case_studies/ai-agent-for-jobs-security.md`
- `public_corpus/case_studies/abm-frontend-architecture.md`
- `public_corpus/case_studies/hermes-buildathon-architecture.md`
- `public_corpus/projects/sparse-model-theory-api.md`
- `public_corpus/writing/`

## Candidate Inventory

| # | Path | Filename | First heading | Category | Recommended action | Reason |
|---:|---|---|---|---|---|---|
| 1 | `/home/rahul_shiv_shankar/Dev/Projects/ABM Agent/abm-system/CLAUDE.md` | `CLAUDE.md` | `# ABM System - Claude Code Instructions` | project | needs Rahul review | Sensitive markers: secret/API key, salary/career, personal conflict, contact info, client/company-confidential. |
| 2 | `/home/rahul_shiv_shankar/Dev/Projects/ABM Agent/abm-system/MATCHING_HANDOFF.md` | `MATCHING_HANDOFF.md` | `## KNOWN BUG (not in match path, do not ship a feature that reads it)` | project | needs Rahul review | Sensitive marker: secret/API key. |
| 3 | `/home/rahul_shiv_shankar/Dev/Projects/ABM Agent/abm-system/agents/voice_rules.md` | `voice_rules.md` | `# ABM System - Global Voice Rules` | project | summarize into public case study | No sensitive markers from scan; likely useful as proof of product/agent design discipline. |
| 4 | `/home/rahul_shiv_shankar/Dev/Projects/AI Agent for Jobs/web-ui/README.md` | `README.md` | `## Installation Guide` | project | needs Rahul review | Sensitive markers: contact info, client/company-confidential. |
| 5 | `/home/rahul_shiv_shankar/Dev/Projects/AI Agent for Jobs/web-ui/SECURITY.md` | `SECURITY.md` | `## Reporting Security Issues` | project | summarize into public case study | No sensitive markers from scan; likely useful as evidence of security/reporting hygiene. |
| 6 | `/home/rahul_shiv_shankar/Dev/Projects/abm-frontend/AGENTS.md` | `AGENTS.md` | `# This is NOT the Next.js you know` | project | summarize into public case study | No sensitive markers from scan; likely useful as evidence of frontend architecture constraints. |
| 7 | `/home/rahul_shiv_shankar/Dev/Projects/abm-frontend/CLAUDE.md` | `CLAUDE.md` | `(none)` | unknown | needs Rahul review | Insufficient confidence from filename/heading. |
| 8 | `/home/rahul_shiv_shankar/Dev/Projects/abm-frontend/README.md` | `README.md` | `## Getting Started` | project | needs Rahul review | Sensitive marker: personal conflict. |
| 9 | `/home/rahul_shiv_shankar/Dev/Projects/abm-frontend/SETUP_AUTH.md` | `SETUP_AUTH.md` | `# Auth setup (Clerk) - Sahayak` | project | needs Rahul review | Sensitive markers: secret/API key, contact info, client/company-confidential. |
| 10 | `/home/rahul_shiv_shankar/Dev/Projects/hermes-buildathon/AGENTS.md` | `AGENTS.md` | `# This is NOT the Next.js you know` | project | summarize into public case study | No sensitive markers from scan; likely useful as evidence of buildathon/frontend architecture constraints. |
| 11 | `/home/rahul_shiv_shankar/Dev/Projects/hermes-buildathon/CLAUDE.md` | `CLAUDE.md` | `(none)` | unknown | needs Rahul review | Insufficient confidence from filename/heading. |
| 12 | `/home/rahul_shiv_shankar/Dev/Projects/hermes-buildathon/README.md` | `README.md` | `## Getting Started` | project | needs Rahul review | Sensitive marker: personal conflict. |
| 13 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/README.md` | `README.md` | `# Sparse Model Theory` | project | needs Rahul review | Sensitive marker: client/company-confidential. Could still be public-safe, but review before merging with current corpus. |
| 14 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/STATUS.md` | `STATUS.md` | `# Sparse Model Theory Prototype Status` | proof of work | needs Rahul review | Sensitive markers: secret/API key, client/company-confidential. |
| 15 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/api/README.md` | `README.md` | `# Sparse Model Theory API` | project | summarize into public case study | No sensitive markers from scan; useful as API/backend proof. |
| 16 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/examples/2026-07-27-career-switch-pressure.md` | `2026-07-27-career-switch-pressure.md` | `Career switch under pressure` | proof of work | needs Rahul review | Sensitive markers: salary/career, contact info. |
| 17 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/examples/2026-07-27-pain-led-product.md` | `2026-07-27-pain-led-product.md` | `Personal pain beats abstract market maps` | proof of work | needs Rahul review | Sensitive markers: personal conflict, contact info. |
| 18 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/examples/2026-07-27-sahayak-shelved.md` | `2026-07-27-sahayak-shelved.md` | `Sahayak shelved - no moat` | project | needs Rahul review | Sensitive marker: contact info. |
| 19 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/2026-06-querylens-traction-failure.md` | `2026-06-querylens-traction-failure.md` | `QueryLens - no traction, wrong ICP and distribution` | private/sensitive | needs Rahul review | Private notes path; list only for review. No import without explicit approval and sanitization. |
| 20 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/2026-07-17-sahayak-shelved.md` | `2026-07-17-sahayak-shelved.md` | `Sahayak shelved - no moat` | private/sensitive | needs Rahul review | Private notes path; list only for review. No import without explicit approval and sanitization. |
| 21 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/2026-07-27-career-switch-pressure.md` | `2026-07-27-career-switch-pressure.md` | `Career switch under pressure` | private/sensitive | needs Rahul review | Private notes path; list only for review. No import without explicit approval and sanitization. |
| 22 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/2026-07-cadence-title-mismatch.md` | `2026-07-cadence-title-mismatch.md` | `Cadence title doesn't pattern-match CoS/Founder's Office filters` | private/sensitive | needs Rahul review | Private notes path; list only for review. No import without explicit approval and sanitization. |
| 23 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/2026-07-whole-truth-reddit-accusation.md` | `2026-07-whole-truth-reddit-accusation.md` | `Accusation thread outperforms rebuttal - algorithmic amplification vs resolution` | private/sensitive | needs Rahul review | Private notes path; list only for review. No import without explicit approval and sanitization. |
| 24 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/README.md` | `README.md` | `# Sparse Model Theory` | project | needs Rahul review | Sensitive marker: client/company-confidential. Could still be public-safe, but review before merging with current corpus. |
| 25 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/STATUS.md` | `STATUS.md` | `# Sparse Model Theory Prototype Status` | proof of work | needs Rahul review | Sensitive markers: secret/API key, client/company-confidential. |
| 26 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/api/README.md` | `README.md` | `# Sparse Model Theory API` | project | summarize into public case study | No sensitive markers from scan; duplicate/sibling of Sparse Model Theory API docs, likely merge target. |
| 27 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/docs/openclaw_demo.md` | `openclaw_demo.md` | `# OpenClaw Demo Endpoint` | project | needs Rahul review | Sensitive markers: secret/API key, daily capture, client/company-confidential. |
| 28 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/docs/public_portfolio.md` | `public_portfolio.md` | `# Public Portfolio Split` | project | needs Rahul review | Contains private-boundary terms and API-key warnings by design; use as internal docs, not import material. |
| 29 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/examples/2026-07-27-career-switch-pressure.md` | `2026-07-27-career-switch-pressure.md` | `Career switch under pressure` | proof of work | needs Rahul review | Sensitive markers: salary/career, contact info. |
| 30 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/examples/2026-07-27-pain-led-product.md` | `2026-07-27-pain-led-product.md` | `Personal pain beats abstract market maps` | proof of work | needs Rahul review | Sensitive markers: personal conflict, contact info. |
| 31 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/examples/2026-07-27-sahayak-shelved.md` | `2026-07-27-sahayak-shelved.md` | `Sahayak shelved - no moat` | project | needs Rahul review | Sensitive marker: contact info. |
| 32 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/README.md` | `README.md` | `# Public Corpus` | proof of work | ignore | Already in public corpus; do not re-import. |
| 33 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/caveats.md` | `caveats.md` | `# Caveats` | proof of work | ignore | Already in public corpus; do not re-import. |
| 34 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/profile.md` | `profile.md` | `# Rahul Profile` | proof of work | ignore | Already in public corpus; do not re-import. |
| 35 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/projects/akshar.md` | `akshar.md` | `# Akshar` | proof of work | ignore | Already in public corpus; do not re-import. |
| 36 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/projects/openclaw-demo.md` | `openclaw-demo.md` | `# OpenClaw Demo` | proof of work | ignore | Already in public corpus; do not re-import. |
| 37 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/projects/sahayak.md` | `sahayak.md` | `# Sahayak` | proof of work | ignore | Already in public corpus; do not re-import. |
| 38 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/projects/second-brain-console.md` | `second-brain-console.md` | `# Second Brain Console` | proof of work | ignore | Already in public corpus; do not re-import. |
| 39 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/projects/sparse-model-theory.md` | `sparse-model-theory.md` | `# Sparse Model Theory` | proof of work | ignore | Already in public corpus; do not re-import. |
| 40 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/proof-of-work.md` | `proof-of-work.md` | `# Proof Of Work` | proof of work | ignore | Already in public corpus; do not re-import. |
| 41 | `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory-openclaw-demo/public_corpus/role-fit.md` | `role-fit.md` | `# Role Fit` | proof of work | ignore | Already in public corpus; do not re-import. |

## Files Needing Sanitization Or Rahul Review

Do not import these without Rahul approval:

- All files under `/home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/notes/`.
- Example notes mentioning career pressure, personal pain, or Sahayak shelving.
- `STATUS.md` files until any API-key/provider/config references are stripped.
- Auth/security/setup files that may include contact info, secrets guidance, client details, or deployment assumptions.
- Internal agent/Claude instruction files with unclear public status.

## Approval Gate

Before importing anything, Rahul should approve one of:

- `safe-engineering-batch`: candidates 3, 5, 6, 10, 15, and 26 as sanitized summaries only.
- `sparse-api-only`: candidates 15 and 26 merged into `public_corpus/projects/sparse-model-theory-api.md`.
- `review-private-projects`: manually review the private/project-sensitive files before any public summary is drafted.

No public corpus files should be overwritten without showing a diff first.
