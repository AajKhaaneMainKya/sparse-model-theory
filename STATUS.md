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
