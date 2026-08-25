# Static Vercel Deploy

Vercel should host only the public static portfolio frontend. FastAPI remains on Railway.

## Why Root Deploy Failed

The repository root contains `api/server.py`, `requirements.txt`, `engine/`, tests, local data, and private/admin surfaces. A root `vercel` deploy detected the FastAPI backend and tried to bundle Python dependencies into a Vercel function, which exceeded the 500 MB function limit.

## Correct Deploy Folder

Deploy only:

```text
vercel_public/
```

This folder contains only:

```text
index.html
styles.css
app.js
vercel.json
README.md
```

## Railway Rewrite

The public frontend calls:

```text
/api/ask-rahul
```

`vercel_public/vercel.json` rewrites `/api/:path*` to Railway:

```json
{
  "source": "/api/:path*",
  "destination": "https://replace-with-railway-backend-domain.up.railway.app/:path*"
}
```

Replace `https://replace-with-railway-backend-domain.up.railway.app` with the real Railway backend domain before production.

## Deploy Command

```bash
cd vercel_public
vercel --prod
```

Do not run `vercel --prod` from the repo root.

## Public Surface

The Vercel app includes public routes:

```text
/
/projects
/ask
/contact
```

It does not include `/console`, `/admin`, backend source, tests, notes, or `public_corpus/`.
