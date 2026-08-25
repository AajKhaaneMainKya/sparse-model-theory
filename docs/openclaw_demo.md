# OpenClaw Demo Endpoint

This experiment adds a single OpenClaw-facing endpoint:

```text
POST /openclaw/agent
```

It accepts compact chat commands and routes them into the existing Sparse Model Theory daily-capture and agentic second-brain flows. It is meant to feel open-ended in a demo, but it does not expose arbitrary tools.

## Request Shape

```json
{
  "message": "Should I build a compliance product for fleet operators?",
  "mode": "balanced",
  "return_full": false,
  "allow_capture": true,
  "skip_skills": []
}
```

`mode` may be `economy`, `balanced`, or `deep`.

## Commands

```text
/capture Today I noticed founder-led services sell better when the buyer already feels exposed.
/think Should I build a compliance product for fleet operators?
/followup What are the biggest missing assumptions?
```

If the message does not start with a command, it is treated like `/think`.

`/followup` wraps the message as:

```text
Follow-up question: {message}
```

and uses the same existing agentic second-brain flow, including today's daily capture when present.

## Curl Examples

Local server:

```bash
curl -s http://127.0.0.1:8001/openclaw/agent \
  -H 'content-type: application/json' \
  -d '{"message":"/capture Today I noticed founder-led services sell better when the buyer already feels exposed."}'
```

```bash
curl -s http://127.0.0.1:8001/openclaw/agent \
  -H 'content-type: application/json' \
  -d '{"message":"/think Should I build a compliance product for fleet operators?","mode":"economy"}'
```

```bash
curl -s http://127.0.0.1:8001/openclaw/agent \
  -H 'content-type: application/json' \
  -d '{"message":"Should I build a compliance product for fleet operators?","mode":"balanced","return_full":true}'
```

```bash
curl -s http://127.0.0.1:8001/openclaw/agent \
  -H 'content-type: application/json' \
  -d '{"message":"/followup What are the biggest missing assumptions?","mode":"balanced"}'
```

## Local Notes

Start the experiment server on a non-production port:

```bash
python3 -m uvicorn api.server:app --host 127.0.0.1 --port 8001
```

If using the original virtualenv from the main checkout, activate or recreate one in this worktree first.

## Railway Notes

Do not deploy this experiment automatically.

The current production-sensitive deploy setup is `Procfile` only:

```text
web: uvicorn api.server:app --host 0.0.0.0 --port $PORT
```

No `railway.json`, `Dockerfile`, or `nixpacks.toml` is present in this branch at the time of this experiment.

The experiment would need these environment variables on Railway:

```text
OPENAI_API_KEY
ZONE_PROVIDER
OPENAI_MODEL
OPENAI_MODEL_ECONOMY
OPENAI_MODEL_BALANCED_REASONING
OPENAI_MODEL_DEEP
```

`SMT_DB_PATH` should continue to point at the mounted Railway volume if session persistence is used elsewhere. The OpenClaw endpoint itself does not write sessions, but `/daily-capture` still writes under the existing notes path.

No Procfile, Dockerfile, or start command change was made for this experiment. If deployment changes become necessary, propose the diff separately before editing production deployment files.

## Safety Boundaries

The endpoint does not provide:

- shell commands
- arbitrary file reads
- file deletion
- outbound messages
- web search
- direct schema-note writes
- arbitrary tool execution

The only write exposed by this endpoint is daily capture, and only through the existing daily-capture function/path. Set `allow_capture=false` to disable that write for a request.

Schema notes remain human-approved. `anchor_type` remains human-approved and must not be inferred.
