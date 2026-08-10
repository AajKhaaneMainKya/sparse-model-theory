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

### Thread-handling decision (capture now, organize later)

- `thread_id` is **OPTIONAL** on `POST /second-brain`. Omitted -> auto-create or
  reuse a thread named "Uncategorized". Provided but nonexistent -> `404` (an
  explicit id signals explicit intent; only the omitted case auto-creates).
- `PATCH /sessions/{id}` `{ "thread_id" }` re-threads an existing session, so a
  session captured into "Uncategorized" can be organized afterward. Moving to a
  nonexistent thread -> `404`.

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
