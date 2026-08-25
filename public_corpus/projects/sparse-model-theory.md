# Sparse Model Theory

Sparse Model Theory is a local-first prototype for a personal sparse thinking engine. Its v1 contract uses Markdown notes with YAML frontmatter, a mandatory human-set `anchor_type`, deterministic gate routing, and retrieval only after the route is known.

Public proof in this repository shows deterministic routing, a note schema, semantic retrieval over contested notes, and a boundary between fixed structural paths and precedent retrieval. It is relevant agentic systems evidence because the model-facing behavior is bounded by deterministic routing and explicit schemas before any retrieval or model reasoning occurs. Tests cover note parsing, retrieval behavior, routing, and schema constraints.

The project demonstrates a preference for bounded orchestration: let simple deterministic rules decide the path first, then use retrieval or model calls only where they are appropriate.
