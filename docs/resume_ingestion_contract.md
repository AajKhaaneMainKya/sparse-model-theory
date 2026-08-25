# Resume Ingestion Contract

Ask Rahul treats uploaded resumes as public evidence only after they are written under `public_corpus/`.

## Artifacts

Each accepted resume upload creates two durable artifacts:

- `public_corpus/resumes/{slug}.md`: human-readable Markdown for review and public evidence display.
- `public_corpus/resumes/_facts/{slug}.json`: structured public facts used first for factual Ask Rahul answers.

Temporary, fixture, verification, and test labels such as `section-retrieval-test`, `temp`, `tmp`, `fixture`, and `verification` are rejected or excluded from retrieval.

## JSON Fact Schema

The fact artifact uses this shape:

```json
{
  "schema_version": 1,
  "source_resume": "resumes/example.md",
  "source_title": "Rahul Shiv Shankar — Resume: example",
  "facts": [
    {
      "id": "education-abc123",
      "category": "education",
      "value": "BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\nMBA, Leadership and Strategy",
      "source_resume": "resumes/example.md",
      "source_section": "Education",
      "evidence_text": "BITSoM (BITS Pilani School of Management), Mumbai 2021 -- 2023\nMBA, Leadership and Strategy",
      "confidence": "high"
    }
  ],
  "warnings": []
}
```

Supported categories are `identity`, `contact`, `location`, `links`, `summary`, `education`, `work_experience`, `projects`, `skills`, `tools`, `domains`, `achievements`, `metrics`, `communities`, `dates`, `roles`, and `organizations`.

Confidence is `high`, `medium`, or `low`. Missing core sections such as summary, education, work experience, projects, or skills produce warnings in the upload response and JSON artifact.

## Ask Rahul Usage

For factual resume questions, Ask Rahul loads `public_corpus/resumes/_facts/*.json` first. Markdown resumes are still available for synthesis and display, and older Markdown-only resumes are parsed as a fallback when no matching JSON facts exist.

If structured facts conflict across resume variants, Ask Rahul surfaces the conflict instead of silently choosing one. MBA answers must come from Education evidence; Regenesys can be cited as a workplace only unless an Education fact explicitly says otherwise.

## Safe Re-Ingestion

Upload through `/admin/resume-upload` with an optional label. The label becomes the slug used for both artifacts. Duplicate labels append a timestamp instead of overwriting existing evidence.

Do not manually place scratch files in `public_corpus/resumes/`. Use `tests/fixtures/` or a temporary directory for verification artifacts. Do not put private notes, raw uploads, `.env` files, source code, tests, or internal material under `public_corpus/`.
