# Public Portfolio V1 Operations

The public portfolio UI is static. Vercel should deploy only `vercel_public/`.
FastAPI, database writes, Ask Rahul, contact requests, admin auth, and resume
ingestion stay on Railway.

## Contact Notifications

Contact requests are written to the app database before notification is
attempted. Notification failure does not fail the public request and does not
expose provider details to the visitor.

Supported provider:

- `CONTACT_NOTIFY_PROVIDER=resend`
- `RESEND_API_KEY`
- `CONTACT_NOTIFY_TO`
- `CONTACT_NOTIFY_FROM`

If any notification variable is missing, the request is stored and notification
is marked as skipped internally.

## Admin Auth

Admin pages and APIs require `ADMIN_PASSWORD` or `ADMIN_TOKEN`.

Protected routes include:

- `/admin`
- `/admin/resumes`
- `/admin/dashboard-data`
- `/admin/resume-upload`
- `/admin/contact-requests`
- `/admin/public-question-logs`

In production or Railway, admin routes fail closed if neither admin secret is
configured. The admin login flow uses an httpOnly cookie; admin secrets are not
embedded in frontend JavaScript.

## Public Boundary

Ask Rahul evidence is limited to `public_corpus/` and structured resume facts in
`public_corpus/resumes/_facts/`. Private notes, daily captures, raw uploads,
environment files, source files, and tests must not be used as public evidence.

## Vercel

Deploy from:

```bash
cd /home/rahul_shiv_shankar/Dev/Projects/sparse-model-theory/vercel_public
vercel --prod
```

Do not run Vercel from the repository root.
