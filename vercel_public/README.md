# Static Vercel Deployment

This folder is the only folder to deploy to Vercel.

Do not deploy the repository root to Vercel. The repo root contains the FastAPI backend, Python dependencies, tests, private/admin UI, and Railway runtime files. Deploying the root can make Vercel try to bundle the backend as a serverless function.

## Deploy

```bash
cd vercel_public
vercel --prod
```

## Backend

The FastAPI backend lives on Railway. The static frontend calls:

```text
/api/ask-rahul
```

Vercel rewrites that to Railway using `vercel.json`.

Before production, replace this placeholder in `vercel.json`:

```text
https://replace-with-railway-backend-domain.up.railway.app
```

with the real Railway backend domain. Keep the `/:path*` suffix.

This folder intentionally does not include `api/`, `engine/`, `tests/`, `.venv/`, `requirements.txt`, `notes/`, `public_corpus/`, the private console, or the admin upload UI.
