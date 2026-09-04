"""Client for Akshar's headless content-generation API.

Calls the persistently-deployed Akshar planner service (see
~/Dev/claude-writing-agent, railway/planner_api.py: POST /job/headless,
then poll GET /job/headless/<job_id>/status). A full pipeline run has been
confirmed to take up to ~15-16 minutes end to end, so generate_draft()
blocks for that whole duration -- callers must run it in a background
thread, never directly inside a request handler.

Uses stdlib urllib only, matching this repo's existing convention (see
_notify_contact_request in api/server.py) -- no new HTTP-client dependency.
"""
from __future__ import annotations

import json
import logging
import os
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)

# Confirmed live via a real end-to-end test call during this task (HTTP 200
# on /health, a real job created and completed). Overridable via env var in
# case the service is ever redeployed under a different URL.
AKSHAR_PLANNER_URL = os.environ.get(
    "AKSHAR_PLANNER_URL", "https://akshar-planner-uat-production.up.railway.app"
).rstrip("/")

# Dedicated internal identity for the daily-drafting pipeline, exempted from
# Akshar's 5-article free cap in integrations/supabase_client.py's
# EXEMPT_USERS set (claude-writing-agent repo). NOTE: that exemption is a
# local code change made during this task -- it only takes effect on the
# live Railway service once that repo is redeployed, which this session has
# no way to trigger. Until then, this identity rides the same default
# 5-calls-ever quota as any other unrecognized user_id.
AKSHAR_INTERNAL_USER_ID = os.environ.get("AKSHAR_INTERNAL_USER_ID", "internal_daily_pipeline")

AKSHAR_POLL_INTERVAL_SECONDS = int(os.environ.get("AKSHAR_POLL_INTERVAL_SECONDS", "12"))
# 20-minute ceiling -- comfortably above the ~15-16 minute real run time
# confirmed during testing, without waiting forever on a genuinely stuck job.
AKSHAR_TIMEOUT_SECONDS = int(os.environ.get("AKSHAR_TIMEOUT_SECONDS", "1200"))


class AksharError(Exception):
    """Raised on any failure to produce a draft -- job error, needs_new_topic,
    timeout, or a transport/HTTP failure. Callers should notify and stop, not
    auto-retry (per the daily-drafting pipeline's explicit no-auto-retry rule)."""


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(url, data=data, headers={"content-type": "application/json"}, method="POST")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: int) -> dict:
    req = urlrequest.Request(url, method="GET")
    with urlrequest.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def generate_draft(topic: str, word_limit: int = 400, format_type: str = "linkedin") -> dict[str, object]:
    """
    Runs synchronously and blocks for up to AKSHAR_TIMEOUT_SECONDS -- call
    this from a background thread, not from inside a FastAPI request handler.

    Returns {"article": str, "editorial_score": int, "share_url": str,
    "job_id": str} on success. Raises AksharError on any failure.
    """
    try:
        created = _post_json(
            f"{AKSHAR_PLANNER_URL}/job/headless",
            {
                "topic": topic,
                "format": format_type,
                "user_id": AKSHAR_INTERNAL_USER_ID,
                "word_limit": word_limit,
            },
            timeout=30,
        )
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise AksharError(f"Failed to start job: {exc}") from exc

    job_id = created.get("job_id")
    if not job_id:
        raise AksharError(f"No job_id returned from /job/headless: {created}")

    logger.info("akshar_job_started job_id=%s topic=%s", job_id, topic)

    elapsed = 0
    while elapsed < AKSHAR_TIMEOUT_SECONDS:
        time.sleep(AKSHAR_POLL_INTERVAL_SECONDS)
        elapsed += AKSHAR_POLL_INTERVAL_SECONDS

        try:
            status = _get_json(f"{AKSHAR_PLANNER_URL}/job/headless/{job_id}/status", timeout=15)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            logger.warning("akshar_poll_transport_error job_id=%s elapsed_s=%s error=%s", job_id, elapsed, exc)
            continue

        state = status.get("status")
        logger.info("akshar_job_poll job_id=%s status=%s elapsed_s=%s", job_id, state, elapsed)

        if state == "done":
            return {
                "article": status.get("article", ""),
                "editorial_score": status.get("editorial_score", 0),
                "share_url": status.get("share_url", ""),
                "job_id": job_id,
            }
        if state in ("error", "needs_new_topic"):
            raise AksharError(f"Job {job_id} failed: {status.get('error', state)}")

    raise AksharError(f"Job {job_id} timed out after {elapsed}s (ceiling {AKSHAR_TIMEOUT_SECONDS}s)")
