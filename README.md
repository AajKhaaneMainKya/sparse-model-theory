# Sparse Model Theory

Local-first prototype for a personal sparse thinking engine.

The v1 contract is intentionally small:

- notes are markdown files with YAML frontmatter
- `anchor_type` is human-set and mandatory
- the gate routes deterministically with no model calls
- fixed notes go to the structural path
- contested notes go to precedent retrieval

This repository is engine-only. Personal notes should live outside the repo or in a
gitignored `notes/` directory.

## Quick Start

```powershell
python -m engine.cli route examples
python -m engine.cli query examples --anchor-type contested --text "Should I take a job or keep building?"
```

## Project Shape

- `engine/note.py`: note loading and schema validation
- `engine/gate.py`: deterministic route selection
- `engine/retrieval.py`: dependency-free lexical precedent matcher
- `engine/cli.py`: local command line harness
- `examples/`: synthetic notes safe to publish
- `tests/`: unit tests for the routing contract

## Design Stance

This is not an identity replacement. It is a consent-bound instrument for preserving
Rahul's judgment patterns under stress, fatigue, or context loss.
