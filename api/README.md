# Sparse Model Theory API

Run from the repository root inside the project `.venv`:

```bash
.venv/bin/uvicorn api.server:app --reload --port 8000
```

Equivalent after activating the same environment:

```bash
uvicorn api.server:app --reload --port 8000
```

This must use the same `.venv` as the rest of the project because the engine depends on installed packages such as `sentence-transformers`.

The local static UI in `ui/index.html` calls `http://localhost:8000`.
