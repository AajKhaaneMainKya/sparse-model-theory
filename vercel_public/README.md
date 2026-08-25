# Static Vercel Deployment

This folder is the only folder to deploy to Vercel.

Do not deploy the repository root to Vercel. Deploying only this folder keeps Vercel static and lets Railway handle the backend.

## Deploy

```bash
cd vercel_public
vercel --prod
```

## Backend

The FastAPI backend lives on Railway. The static frontend calls:

```text
/api/ask-rahul
/api/thinking-window
/api/contact-request
```

Vercel rewrites that to Railway using `vercel.json`.

Keep the Railway destination current in `vercel.json`, including the `/:path*` suffix.
