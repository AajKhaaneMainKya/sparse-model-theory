# Sparse Model Theory Prototype Status

## Applied So Far

- `engine/note.py`: hand-rolled YAML parser replaced with `yaml.safe_load`.
- `engine/retrieval.py`: bag-of-words cosine replaced with cached MiniLM sentence-transformer embeddings.
- `engine/retrieval.py`: `MatchResult` and `MatchTier` added with `NO_MATCH`, `WEAK_MATCH`, and `STRONG_MATCH`.
- `engine/retrieval.py`: `STRONG_MATCH_THRESHOLD = 0.30` exists as a placeholder and is explicitly unvalidated against real data.
- `engine/retrieval.py`: `embed()` is cached with `lru_cache(maxsize=1024)`, keyed on text content, not just the model. This is a deliberate prototype placeholder until note volume justifies a real note-id + content-hash keyed index.
- `requirements.txt`: created with `PyYAML` and `sentence-transformers`.
- `tests/test_note_retrieval.py`: created. It covers YAML edge cases, including hash/colon/nested-list parsing and empty frontmatter, plus semantic retrieval cases for vocabulary-mismatch matching, unrelated-query no-match behavior, and weak-match distinguishability.
- `tests/test_gate.py`: updated for the `MatchResult` return type as a narrow consequence of the `retrieval.py` API change.

## SQLite Session Persistence

- `api/db.py`: stdlib `sqlite3` persistence (no ORM). Tables `threads` and `sessions`
  (FK `sessions.thread_id -> threads(id)`), index `idx_sessions_thread_created` on
  `(thread_id, created_at)`. DB at `data/sparse_model_theory.db` (gitignored via
  `data/`), overridable with `SMT_DB_PATH`. Schema is created lazily per path.
- `sessions.raw_output_json` stores the FULL analysis payload as JSON; `input_text`
  stores the FULL input (only `list_sessions()` truncates for display, never the
  stored row). Nothing about a session is persisted lossily.
- `api/server.py` endpoints: `POST /threads`, `GET /threads`,
  `GET /threads/{id}/sessions`, `GET /sessions/{id}`, and session writes on
  `POST /second-brain`.

### Compressed summaries + opt-in thread context injection

- `sessions.summary TEXT` column added. Generated once at session write-time via a
  single cheap economy-model call (`zone.summarize_session`, 2-4 sentences). Stored
  alongside (not replacing) `raw_output_json`. `input_text` remains full/un-truncated.
- Schema change is handled by `scripts/migrate_add_summary.py`: it is SMT_DB_PATH-aware
  (migrates the local db AND the Railway volume db), backs up `<db>.bak-<UTC>` first,
  then runs a non-destructive `ALTER TABLE ... ADD COLUMN` only if missing (idempotent,
  never drops rows). The app also self-heals via `db._ensure_session_columns()` on first
  connect (additive ADD COLUMN only), so a forgotten migration can't corrupt data.
- `POST /second-brain` gains `include_thread_context: bool` (DEFAULT FALSE). When true,
  the 2 most recent session summaries are compressed (per-summary and total token caps)
  and injected ONCE — into scope_check (fixed) or the planning pass (agentic); downstream
  passes reference it rather than re-receiving it. Off by default = nothing fetched, no
  added tokens. Measured added cost (Ollama usage): 153 -> 312 prompt tokens (+159).
- `+ThreadName` shorthand in the input: stripped from the analyzed text, resolved by
  case-insensitive exact match (fuzzy only to *suggest* on miss), overrides the selected
  thread, and implicitly sets include_thread_context=true. An unresolved name returns a
  clarifying 400 ("did you mean …?") and does not run — never auto-creates/guesses.

### Thread-handling decision (capture now, organize later)

- `thread_id` is **OPTIONAL** on `POST /second-brain`. Omitted -> auto-create or
  reuse a thread named "Uncategorized". Provided but nonexistent -> `404` (an
  explicit id signals explicit intent; only the omitted case auto-creates).
- `PATCH /sessions/{id}` `{ "thread_id" }` re-threads an existing session, so a
  session captured into "Uncategorized" can be organized afterward. Moving to a
  nonexistent thread -> `404`.

## Deployment (Railway)

- **Railway deployment — requires `OPENAI_API_KEY` env var set on Railway, requires
  a persistent volume mounted for the SQLite db path, local Ollama path will report
  unavailable (expected, no GPU/Ollama on Railway).**
- `Procfile`: `web: uvicorn api.server:app --host 0.0.0.0 --port $PORT`. Railway
  injects `$PORT` at runtime; the port is never hardcoded. `api/server.py` also has
  a `__main__` block that reads `PORT` (fallback `8000`) for `python -m api.server`.
- `SMT_DB_PATH` is read from the environment (`api/db.py:_db_path()`); point it at the
  mounted volume, e.g. `SMT_DB_PATH=/data/sparse_model_theory.db`. It is NOT hardcoded
  to a local path (the local default `data/sparse_model_theory.db` is only a fallback).
- `OLLAMA_URL` is env-overridable; when unreachable (the Railway case) the Ollama
  provider returns a clean "Ollama is not available in this environment" message
  instead of hanging or leaking a raw socket error. Use `ZONE_PROVIDER=openai` there.

## Not Verified Yet

- The full test suite has not been run successfully.
- Original verification on Windows failed twice:
  - first on a global pip install permission error;
  - then on a Windows long-path limit while installing `torch` inside `.venv`.
- The project was moved to WSL2 on a native ext4 filesystem specifically to avoid this class of Windows path-length problem.
- No semantic regression scores have been observed yet from the vocabulary-mismatch test's `print()` output.
- The `0.30` threshold in `retrieval.py` is unvalidated against any real score.
- `requirements.txt` has not successfully installed in any environment yet.

## Open Follow-Ups

- Recalibrate the `0.30` threshold once real scores are seen and once real, non-synthetic notes exist.
- Add an exact-boundary test for `score == 0.30` only after extracting a deterministic `tier_for_score()` helper. Do not try to force MiniLM to produce an exact float.
- Replace text-keyed `lru_cache` embedding reuse with a proper note-id + content-hash based index if note count grows.
- **Thread auto-suggestion via existing embedding infrastructure — not yet built,
  schema supports it.** A future pass can run the existing MiniLM pipeline
  (`engine/retrieval.py`) against `sessions.input_text` to suggest likely-matching
  threads for an "Uncategorized" session. No schema change is required: `input_text`
  is stored full and un-truncated, which is what good embeddings need. This is a
  documented future phase only; do not build the suggestion logic yet.
