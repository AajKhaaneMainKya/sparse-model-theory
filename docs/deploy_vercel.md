# Deploy the Public Portfolio to Vercel

This deployment is only for the public portfolio and Ask Rahul UI. The FastAPI backend stays on Railway.

## Architecture

- Vercel serves the static public frontend from `web/`.
- Railway serves the FastAPI backend.
- The browser calls `/api/ask-rahul`.
- Vercel rewrites `/api/:path*` to the Railway backend, so `/api/ask-rahul` becomes `https://<RAILWAY_BACKEND_DOMAIN>/ask-rahul`.

The Vercel app must not expose `/console`, `/admin`, `/notes`, `/daily-capture`, `/second-brain`, `/threads`, `/sessions`, `/present-future`, `/query`, `/openclaw/agent`, or `/notes/upload` unless those routes are explicitly protected first.

## Files

- `web/index.html`: public portfolio shell for `/`, `/projects`, `/ask`, and `/contact`.
- `web/app.js`: public frontend logic. It calls only `/api/ask-rahul`.
- `web/styles.css`: public portfolio styling.
- `web/vercel.json`: Vercel rewrites and public route fallback.

## Required Railway Backend URL

Use the Railway public HTTPS domain for the FastAPI service, for example:

```text
https://your-service-name.up.railway.app
```

Before deploying, edit `web/vercel.json` and replace:

```text
https://replace-with-railway-backend-domain.up.railway.app
```

with the real Railway backend origin. Keep the `/:path*` suffix:

```json
{
  "source": "/api/:path*",
  "destination": "https://your-service-name.up.railway.app/:path*"
}
```

Do not include a trailing slash before `/:path*`.

## Connect the Repo to Vercel

1. Push this repository to GitHub.
2. In Vercel, create a new project from the GitHub repository.
3. Set the Vercel project root directory to `web`.
4. Leave framework preset as `Other` or static site.
5. Leave build command empty.
6. Leave output directory empty or use the project root default.
7. Deploy.

No frontend environment variables are required for the static Vercel app because it uses `/api` and Vercel rewrites.

## How Rewrites Work

The public frontend sends:

```http
POST /api/ask-rahul
```

Vercel proxies that request to Railway:

```http
POST https://<RAILWAY_BACKEND_DOMAIN>/ask-rahul
```

The browser URL remains on the Vercel domain. This keeps the frontend code stable across local and production URLs.

## CORS

With Vercel rewrites, the browser calls the same Vercel origin, so CORS is usually not involved for the browser request.

If the frontend is changed later to call Railway directly, update FastAPI CORS to allow the production Vercel domain, for example:

```text
https://your-vercel-project.vercel.app
https://your-custom-domain.com
```

Do not broaden CORS just to make private console endpoints public.

## Production Test

After deployment:

1. Open the Vercel URL.
2. Confirm `/`, `/projects`, `/ask`, and `/contact` load without showing `/console` or admin UI.
3. Open `/ask`.
4. Ask: `Has Rahul built agentic systems?`
5. Confirm the response cites public corpus evidence.
6. Ask the trap question: `Has Rahul worked at Google?`
7. Confirm the response says evidence is missing if the public corpus does not support the claim.
8. In browser dev tools, confirm the network request goes to `/api/ask-rahul`, not `localhost`, `127.0.0.1`, `/notes`, `/daily-capture`, or `/second-brain`.

Private notes and daily captures are intentionally excluded from `POST /ask-rahul`; that endpoint reads only `public_corpus/`.
