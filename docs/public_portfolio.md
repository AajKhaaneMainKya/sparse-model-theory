# Public Portfolio Split

This app has two separate surfaces:

- Public portfolio: `/`, `/projects`, `/ask`, `/contact`, and `POST /ask-rahul`.
- Private Second Brain console and APIs: `/console`, `/second-brain`, `/daily-capture`, `/threads`, `/sessions`, `/present-future`, `/query`, and `/openclaw/agent`.

`POST /ask-rahul` only reads Markdown files under `public_corpus/`. It does not use `notes/`, `notes/daily/`, private note loaders, session history, daily captures, or Second Brain retrieval.

Only sanitized public proof belongs in `public_corpus/`. Do not put private notes, daily captures, private reasoning traces, raw logs, API keys, or confidential project details there.

When the public corpus does not support a claim, Ask Rahul should say evidence is missing. The expected failure mode is an honest caveat, not a confident guess.
