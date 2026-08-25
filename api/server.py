from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import difflib
from email.parser import BytesParser
from email.policy import default
from io import BytesIO
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine.gate import route_note
from engine.note import Note, NoteValidationError, load_note, load_notes, parse_frontmatter

from . import db
from . import public_portfolio
from .public_portfolio import AskRahulRequest, ask_rahul
from .zone import (
    DAILY_DIR,
    DEFAULT_OLLAMA_MODEL,
    agentic_second_brain_analysis,
    answer_with_context,
    build_thread_context_block,
    get_latest_daily_capture,
    parse_thread_shorthand,
    second_brain_analysis,
    summarize_session,
)


ROOT = Path(__file__).resolve().parents[1]
NOTES_DIR = ROOT / "notes"
EXAMPLES_DIR = ROOT / "examples"
UI_DIR = ROOT / "ui"
PUBLIC_UI_DIR = ROOT / "public_ui"
ADMIN_UI_DIR = ROOT / "admin_ui"


app = FastAPI(title="Sparse Model Theory API")
logger = logging.getLogger(__name__)
db.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://localhost(:[0-9]+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type", "x-admin-token"],
)
app.mount("/static", StaticFiles(directory=UI_DIR), name="static")
app.mount("/portfolio-static", StaticFiles(directory=PUBLIC_UI_DIR), name="portfolio-static")
app.mount("/admin-static", StaticFiles(directory=ADMIN_UI_DIR), name="admin-static")


@dataclass(frozen=True)
class QueryRouteSubject:
    anchor_type: str


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    anchor_type: Literal["fixed", "contested"]
    notes_source: Literal["notes", "examples"] = "notes"


class DailyCaptureRequest(BaseModel):
    text: str = Field(min_length=1)


class SecondBrainRequest(BaseModel):
    # Optional: omit to capture into the shared "Uncategorized" thread. A provided
    # but nonexistent id is a 404 (explicit id == explicit intent).
    thread_id: str | None = Field(default=None, min_length=1)
    input: str = Field(min_length=1)
    skip_skills: list[str] = []
    mode: Literal["economy", "balanced", "deep"] = "balanced"
    agentic: bool = False
    # Opt-in, default False. When true, the most recent prior session summaries in
    # this thread are compressed and injected once into the initial pass.
    include_thread_context: bool = False


class OpenClawAgentRequest(BaseModel):
    message: str = Field(min_length=1)
    mode: Literal["economy", "balanced", "deep"] = "balanced"
    return_full: bool = False
    allow_capture: bool = True
    skip_skills: list[str] = []


class ThreadCreateRequest(BaseModel):
    name: str = Field(min_length=1)


class SessionMoveRequest(BaseModel):
    thread_id: str = Field(min_length=1)


def note_summary(note: Note) -> dict[str, object]:
    return {
        "id": note.id,
        "title": note.title,
        "anchor_type": note.anchor_type,
        "cluster": note.cluster,
        "domain": note.metadata["domain"],
    }


def match_result_payload(result: MatchResult) -> dict[str, object]:
    return {
        "tier": result.tier.name,
        "matches": [
            {
                "id": match.note.id,
                "title": match.note.title,
                "score": match.score,
            }
            for match in result.matches
        ],
    }


def notes_dir_has_markdown(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.rglob("*.md"))


def load_notes_for_list() -> tuple[str, list[Note]]:
    if notes_dir_has_markdown(NOTES_DIR):
        return "notes", load_notes(NOTES_DIR)
    return "examples", load_notes(EXAMPLES_DIR)


def source_dir(name: Literal["notes", "examples"]) -> Path:
    return NOTES_DIR if name == "notes" else EXAMPLES_DIR


async def uploaded_markdown_text(request: Request) -> str:
    body = await request.body()
    content_type = request.headers.get("content-type", "")

    if content_type.startswith("multipart/form-data"):
        message = BytesParser(policy=default).parsebytes(
            b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
        )

        for part in message.iter_parts():
            disposition = part.get_content_disposition()
            filename = part.get_filename()
            if disposition == "form-data" and filename:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset)

        raise HTTPException(status_code=400, detail="multipart upload must include a file field")

    if not body:
        raise HTTPException(status_code=400, detail="request body is empty")

    charset = "utf-8"
    for item in content_type.split(";"):
        item = item.strip()
        if item.startswith("charset="):
            charset = item.removeprefix("charset=")

    return body.decode(charset)


@dataclass(frozen=True)
class ResumeUpload:
    filename: str
    text: str
    label: str | None


def sanitize_resume_label(label: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return cleaned


def default_resume_label(now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    return f"resume-{timestamp}"


def _timestamp_slug(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%d-%H%M%S")


def _check_admin_upload_allowed(request: Request) -> None:
    token = os.environ.get("ADMIN_TOKEN")
    is_production = os.environ.get("ENV") == "production" or bool(os.environ.get("RAILWAY_ENVIRONMENT"))

    if token:
        supplied = request.headers.get("x-admin-token")
        if supplied != token:
            raise HTTPException(status_code=401, detail="invalid admin token")
        return

    if is_production:
        raise HTTPException(status_code=503, detail="ADMIN_TOKEN is required for admin uploads")


def _decode_part_text(part) -> str:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    return payload.decode(charset)


def extract_pdf_text(payload: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="PDF extraction requires pypdf") from exc

    reader = PdfReader(BytesIO(payload))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(page.strip() for page in pages if page.strip())


def extract_docx_text(payload: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="DOCX extraction requires python-docx") from exc

    document = Document(BytesIO(payload))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    return "\n\n".join(paragraphs)


def extract_resume_text(filename: str, payload: bytes, content_type: str | None = None) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        return payload.decode("utf-8").strip()
    if suffix == ".pdf":
        return extract_pdf_text(payload).strip()
    if suffix == ".docx":
        return extract_docx_text(payload).strip()
    raise HTTPException(status_code=400, detail="only .txt, .md, .pdf, and .docx resume uploads are supported")


async def uploaded_resume(request: Request) -> ResumeUpload:
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith("multipart/form-data"):
        raise HTTPException(status_code=400, detail="resume upload must be multipart/form-data")

    message = BytesParser(policy=default).parsebytes(
        b"Content-Type: " + content_type.encode("utf-8") + b"\r\n\r\n" + body
    )

    filename: str | None = None
    text: str | None = None
    label: str | None = None

    for part in message.iter_parts():
        if part.get_content_disposition() != "form-data":
            continue

        name = part.get_param("name", header="content-disposition")
        part_filename = part.get_filename()
        if part_filename:
            suffix = Path(part_filename).suffix.lower()
            if suffix not in {".txt", ".md", ".pdf", ".docx"}:
                raise HTTPException(
                    status_code=400,
                    detail="only .txt, .md, .pdf, and .docx resume uploads are supported",
                )
            filename = part_filename
            payload = part.get_payload(decode=True) or b""
            text = extract_resume_text(part_filename, payload, part.get_content_type())
        elif name == "label":
            raw_label = _decode_part_text(part).strip()
            label = raw_label or None

    if filename is None or text is None:
        raise HTTPException(status_code=400, detail="multipart upload must include a resume file")
    if not text:
        raise HTTPException(status_code=400, detail="resume file is empty")

    return ResumeUpload(filename=filename, text=text, label=label)


def _unique_resume_path(resumes_dir: Path, label: str, now: datetime | None = None) -> tuple[str, Path]:
    path = resumes_dir / f"{label}.md"
    if not path.exists():
        return label, path

    stamped = f"{label}-{_timestamp_slug(now)}"
    path = resumes_dir / f"{stamped}.md"
    if not path.exists():
        return stamped, path

    counter = 2
    while True:
        candidate = resumes_dir / f"{stamped}-{counter}.md"
        if not candidate.exists():
            return f"{stamped}-{counter}", candidate
        counter += 1


def save_resume_to_public_corpus(upload: ResumeUpload, now: datetime | None = None) -> dict[str, object]:
    resolved_now = now or datetime.now()
    timestamp = resolved_now.isoformat(timespec="seconds")
    raw_label = upload.label or Path(upload.filename).stem
    label = sanitize_resume_label(raw_label) or default_resume_label(resolved_now)
    if public_portfolio.is_contaminated_resume_name(f"{label}.md"):
        raise HTTPException(status_code=400, detail="resume label is reserved for test or temporary artifacts")
    resumes_dir = public_portfolio.PUBLIC_CORPUS_DIR / "resumes"
    resumes_dir.mkdir(parents=True, exist_ok=True)
    final_label, path = _unique_resume_path(resumes_dir, label, resolved_now)
    content = (
        f"# Rahul Shiv Shankar — Resume: {final_label}\n\n"
        "Source: uploaded resume\n"
        f"Original filename: {upload.filename}\n"
        f"Updated: {timestamp}\n\n"
        f"{public_portfolio.normalize_public_text(upload.text)}\n"
    )
    path.write_text(content, encoding="utf-8")
    facts_dir = resumes_dir / public_portfolio.RESUME_FACTS_DIRNAME
    facts_dir.mkdir(parents=True, exist_ok=True)
    facts_path = facts_dir / f"{final_label}.json"
    facts_payload = public_portfolio.build_resume_fact_artifact(
        source_resume=str(path.relative_to(public_portfolio.PUBLIC_CORPUS_DIR)),
        source_title=f"Rahul Shiv Shankar — Resume: {final_label}",
        markdown_text=content,
    )
    facts_path.write_text(json.dumps(facts_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "success": True,
        "label": final_label,
        "source": str(path.relative_to(public_portfolio.PUBLIC_CORPUS_DIR)),
        "facts_source": str(facts_path.relative_to(public_portfolio.PUBLIC_CORPUS_DIR)),
        "path": str(path),
        "facts_path": str(facts_path),
        "fact_count": len(facts_payload["facts"]),
        "warnings": facts_payload["warnings"],
        "character_count": len(upload.text.strip()),
    }


@app.get("/")
def public_home() -> FileResponse:
    return FileResponse(PUBLIC_UI_DIR / "index.html")


@app.get("/projects")
def public_projects() -> FileResponse:
    return FileResponse(PUBLIC_UI_DIR / "index.html")


@app.get("/ask")
def public_ask() -> FileResponse:
    return FileResponse(PUBLIC_UI_DIR / "index.html")


@app.get("/contact")
def public_contact() -> FileResponse:
    return FileResponse(PUBLIC_UI_DIR / "index.html")


@app.get("/admin")
def admin() -> FileResponse:
    return FileResponse(ADMIN_UI_DIR / "index.html")


@app.get("/admin/resumes")
def admin_resumes() -> FileResponse:
    return FileResponse(ADMIN_UI_DIR / "index.html")


@app.get("/console")
def console() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.post("/ask-rahul")
def ask_rahul_endpoint(request: AskRahulRequest) -> dict[str, object]:
    return ask_rahul(request.question.strip())


@app.post("/admin/resume-upload")
async def admin_resume_upload(request: Request) -> dict[str, object]:
    _check_admin_upload_allowed(request)
    upload = await uploaded_resume(request)
    result = save_resume_to_public_corpus(upload)
    return {
        "success": True,
        "label": result["label"],
        "source": result["source"],
        "facts_source": result["facts_source"],
        "fact_count": result["fact_count"],
        "warnings": result["warnings"],
        "character_count": result["character_count"],
    }


@app.get("/zone-status")
def zone_status() -> dict[str, str]:
    provider = os.environ.get("ZONE_PROVIDER", "openai").lower()
    model = (
        os.environ.get("SMT_ZONE_MODEL", "qwen2.5:7b-instruct-q4_K_M")
        if provider == "ollama"
        else os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")
    )
    return {
        "provider": provider,
        "model": model,
    }


@app.get("/notes")
def notes_index() -> dict[str, object]:
    source, notes = load_notes_for_list()
    return {
        "source": source,
        "notes": [note_summary(note) for note in notes],
    }


@app.post("/notes/upload")
async def notes_upload(request: Request) -> dict[str, object]:
    text = await uploaded_markdown_text(request)

    try:
        metadata, _ = parse_frontmatter(text, Path("uploaded-note.md"))
        note_id = str(metadata["id"])
    except KeyError:
        return {"success": False, "error": "uploaded-note.md: missing required fields: ['id']"}
    except NoteValidationError as exc:
        return {"success": False, "error": str(exc)}

    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    path = NOTES_DIR / f"{note_id}.md"
    path.write_text(text, encoding="utf-8")

    try:
        note = load_note(path)
    except NoteValidationError as exc:
        path.unlink(missing_ok=True)
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "note": note_summary(note),
    }


@app.post("/daily-capture")
def daily_capture(request: DailyCaptureRequest) -> dict[str, object]:
    today = date.today().isoformat()
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    path = DAILY_DIR / f"{today}.md"
    timestamp = datetime.now().isoformat(timespec="seconds")

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        separator = f"\n\n---\n\n## Capture {timestamp}\n\n"
        path.write_text(existing.rstrip() + separator + request.text + "\n", encoding="utf-8")
    else:
        text = (
            "---\n"
            f"id: daily-{today}\n"
            f"created_at: {today}\n"
            'source: "daily-capture"\n'
            "---\n\n"
            f"## Capture {timestamp}\n\n"
            f"{request.text}\n"
        )
        path.write_text(text, encoding="utf-8")

    return {
        "success": True,
        "path": str(path),
        "date": today,
    }


def _compact_chat_reply(text: str, max_chars: int = 1400) -> str:
    cleaned = " ".join(text.strip().split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _analysis_reply(payload: dict[str, object]) -> str:
    synthesis = payload.get("synthesis")
    if isinstance(synthesis, dict):
        output = synthesis.get("output")
        if isinstance(output, str) and output.strip():
            return _compact_chat_reply(output)

    scope_output: str | None = None
    results = payload.get("results")
    if isinstance(results, list):
        first_output: str | None = None
        for item in results:
            if not isinstance(item, dict):
                continue
            output = item.get("output")
            if not isinstance(output, str) or not output.strip():
                continue
            if first_output is None:
                first_output = output
            if item.get("skill") == "scope_check":
                scope_output = output
                break
        reply_parts = [part for part in (scope_output, first_output) if part]
        if reply_parts:
            return _compact_chat_reply("\n\n".join(reply_parts))

    return "Analysis completed, but no compact reply was available."


@app.post("/openclaw/agent")
def openclaw_agent(request: OpenClawAgentRequest) -> dict[str, object]:
    started_at = time.perf_counter()
    raw_message = request.message.strip()

    if not raw_message:
        return {
            "kind": "error",
            "reply": "Message is empty.",
            "full_result": None,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        }

    # OpenClaw demo boundary:
    # - no shell/tool execution, web access, outbound messaging, or arbitrary file reads
    # - no schema-note writes and no anchor_type inference
    # - the only write path exposed here is existing daily capture persistence
    if raw_message.startswith("/capture "):
        if not request.allow_capture:
            return {
                "kind": "error",
                "reply": "Capture is disabled for this request.",
                "full_result": None,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
        capture_text = raw_message.removeprefix("/capture ").strip()
        if not capture_text:
            return {
                "kind": "error",
                "reply": "Capture text is empty.",
                "full_result": None,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
            }
        result = daily_capture(DailyCaptureRequest(text=capture_text))
        return {
            "kind": "capture",
            "reply": f"Captured for {result['date']}.",
            "full_result": result if request.return_full else None,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        }

    if raw_message.startswith("/think "):
        input_text = raw_message.removeprefix("/think ").strip()
    elif raw_message.startswith("/followup "):
        rest = raw_message.removeprefix("/followup ").strip()
        input_text = f"Follow-up question: {rest}" if rest else ""
    else:
        input_text = raw_message

    if not input_text:
        return {
            "kind": "error",
            "reply": "Analysis text is empty.",
            "full_result": None,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        }

    daily_capture_text = get_latest_daily_capture()
    payload = agentic_second_brain_analysis(
        input_text,
        daily_capture=daily_capture_text,
        skip_skills=request.skip_skills,
        mode=request.mode,
    )
    payload["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)

    return {
        "kind": "analysis",
        "reply": _analysis_reply(payload),
        "full_result": payload if request.return_full else None,
        "latency_ms": payload["latency_ms"],
    }


def _session_model_summary() -> tuple[str, str]:
    """Provider and default model name recorded on the session, matching /zone-status."""
    provider = os.environ.get("ZONE_PROVIDER", "openai").lower()
    if provider == "ollama":
        return provider, os.environ.get("SMT_ZONE_MODEL", DEFAULT_OLLAMA_MODEL)
    return provider, os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")


@app.post("/threads")
def create_thread(request: ThreadCreateRequest) -> dict[str, object]:
    return db.create_thread(request.name)


@app.get("/threads")
def list_threads() -> dict[str, object]:
    return {"threads": db.list_threads()}


@app.get("/threads/{thread_id}/sessions")
def thread_sessions(thread_id: str) -> dict[str, object]:
    thread = db.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail=f"thread '{thread_id}' not found")
    return {"thread": thread, "sessions": db.list_sessions(thread_id)}


@app.get("/sessions/{session_id}")
def session_detail(session_id: str) -> dict[str, object]:
    session = db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    return session


@app.patch("/sessions/{session_id}")
def patch_session_thread(session_id: str, request: SessionMoveRequest) -> dict[str, str]:
    # Re-thread a session after the fact ("capture now, organize later"). An
    # explicit target that doesn't exist is a 404 (never auto-created here).
    if not db.thread_exists(request.thread_id):
        raise HTTPException(status_code=404, detail=f"thread '{request.thread_id}' not found")
    moved = db.move_session(session_id, request.thread_id)
    if moved is None:
        raise HTTPException(status_code=404, detail=f"session '{session_id}' not found")
    return moved


@app.get("/present-future")
def present_future() -> dict[str, object]:
    """Present/Next timeline built entirely from real stored session data.

    - present: the most recent session (the current state of thinking), summarized.
    - next: the forward-looking synthesis of that same session ("next questions"),
      when it exists (agentic runs produce one). Null otherwise — never fabricated.
    The two figures are linked because next is drawn from the present session.
    """
    threads = db.list_threads()  # most-recently-updated first
    for thread in threads:
        sessions = db.list_sessions(thread["id"])
        if not sessions:
            continue
        latest = db.get_session(sessions[0]["id"])
        if latest is None:
            continue

        input_text = str(latest.get("input_text") or "")
        excerpt = input_text[:180] + ("…" if len(input_text) > 180 else "")
        present = {
            "session_id": latest["id"],
            "thread_id": latest["thread_id"],
            "thread_name": thread["name"],
            "created_at": latest["created_at"],
            "input_excerpt": excerpt,
            "summary": latest.get("summary"),
        }

        next_thought = None
        raw = latest.get("raw_output")
        synthesis = raw.get("synthesis") if isinstance(raw, dict) else None
        if isinstance(synthesis, dict):
            output = synthesis.get("output")
            if isinstance(output, str) and output.strip():
                next_thought = {
                    "session_id": latest["id"],
                    "thread_id": latest["thread_id"],
                    "thread_name": thread["name"],
                    "synthesis": output,
                }

        return {"present": present, "next": next_thought, "linked": next_thought is not None}

    return {"present": None, "next": None, "linked": False}


def _resolve_thread_id(requested_thread_id: str | None) -> str:
    """Optional thread_id: omitted -> Uncategorized; provided-but-missing -> 404."""
    if requested_thread_id is None:
        return db.get_or_create_uncategorized_thread()["id"]
    if not db.thread_exists(requested_thread_id):
        raise HTTPException(
            status_code=404,
            detail=(
                f"thread '{requested_thread_id}' not found; "
                "create it explicitly via POST /threads, or omit thread_id to use Uncategorized"
            ),
        )
    return requested_thread_id


def _close_thread_names(name: str, limit: int = 3) -> list[str]:
    """Case-insensitive fuzzy suggestions for an unresolved '+ThreadName'."""
    names = db.all_thread_names()
    lower_to_original: dict[str, str] = {}
    for original in names:
        lower_to_original.setdefault(original.lower(), original)
    close = difflib.get_close_matches(name.lower(), list(lower_to_original), n=limit, cutoff=0.4)
    return [lower_to_original[match] for match in close]


@dataclass(frozen=True)
class _ResolvedRun:
    input_text: str
    thread_id: str
    include_thread_context: bool
    shorthand_thread: str | None


def _resolve_run(request: SecondBrainRequest) -> _ResolvedRun:
    """Apply the '+ThreadName' shorthand, else fall back to the request fields.

    Shorthand, when it resolves, overrides the selected thread AND implicitly turns
    on thread-context injection (an explicit continuity signal). An unresolved
    shorthand raises a clarifying 400 and never guesses or auto-creates a thread.
    """
    cleaned_text, shorthand_name = parse_thread_shorthand(request.input)

    if shorthand_name is None:
        return _ResolvedRun(
            input_text=request.input,
            thread_id=_resolve_thread_id(request.thread_id),
            include_thread_context=request.include_thread_context,
            shorthand_thread=None,
        )

    if not cleaned_text:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nothing to analyze after removing the '+{shorthand_name}' thread shorthand — "
                "include the text you want analyzed alongside it."
            ),
        )

    match = db.find_thread_by_name(shorthand_name)
    if match is None:
        suggestions = _close_thread_names(shorthand_name)
        hint = ", ".join(suggestions) if suggestions else "none — create it first via POST /threads"
        raise HTTPException(
            status_code=400,
            detail=f"No thread found matching '{shorthand_name}' — did you mean one of: [{hint}]?",
        )

    return _ResolvedRun(
        input_text=cleaned_text,
        thread_id=match["id"],
        include_thread_context=True,  # explicit intent via shorthand
        shorthand_thread=match["name"],
    )


@app.post("/second-brain")
def second_brain(request: SecondBrainRequest) -> dict[str, object]:
    resolved = _resolve_run(request)
    input_text = resolved.input_text
    thread_id = resolved.thread_id

    # Opt-in, cost-controlled thread context. Off by default => nothing fetched,
    # nothing injected, same token cost as before this feature existed.
    thread_context: str | None = None
    if resolved.include_thread_context:
        summaries = db.recent_summaries(thread_id, limit=2)
        thread_context = build_thread_context_block(summaries) or None

    started_at = time.perf_counter()
    # Snapshot the daily capture up front so the exact text used is what we persist.
    daily_capture = get_latest_daily_capture()
    if request.agentic:
        payload = agentic_second_brain_analysis(
            input_text,
            daily_capture=daily_capture,
            skip_skills=request.skip_skills,
            mode=request.mode,
            thread_context=thread_context,
        )
    else:
        payload = second_brain_analysis(
            input_text,
            daily_capture=daily_capture,
            skip_skills=request.skip_skills,
            mode=request.mode,
            thread_context=thread_context,
        )
    payload["latency_ms"] = round((time.perf_counter() - started_at) * 1000, 1)

    # One cheap summary call at write-time, feeding the compressed thread memory.
    summary = summarize_session(input_text, payload, mode=request.mode)

    provider, model_name = _session_model_summary()
    session = db.add_session(
        thread_id=thread_id,
        mode="agentic" if request.agentic else "fixed",
        input_text=input_text,
        daily_capture=daily_capture,
        model_provider=provider,
        model_name=model_name,
        thinking_mode=request.mode,
        latency_ms=payload["latency_ms"],
        raw_output=payload,
        summary=summary,
    )
    payload["session_id"] = session["id"]
    payload["thread_id"] = thread_id
    payload["thread_context_injected"] = thread_context is not None
    if resolved.shorthand_thread is not None:
        payload["shorthand_thread"] = resolved.shorthand_thread
    logger.info(
        "POST /second-brain wrote session %s to thread %s (context_injected=%s) in %.1f ms",
        session["id"],
        thread_id,
        thread_context is not None,
        payload["latency_ms"],
    )
    return payload


@app.post("/query")
def query(request: QueryRequest) -> dict[str, object]:
    from engine.retrieval import MatchTier, precedent_matches

    started_at = time.perf_counter()

    try:
        notes = load_notes(source_dir(request.notes_source))
        route = route_note(QueryRouteSubject(anchor_type=request.anchor_type))

        if route.path == "structural-match":
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            logger.info("POST /query completed in %.1f ms", elapsed_ms)
            raise HTTPException(status_code=501, detail="structural-match not implemented yet")

        result = precedent_matches(request.query, notes)
        payload = {
            "route": {
                "path": route.path,
                "reason": route.reason,
            },
            "result": match_result_payload(result),
        }

        if result.tier in {MatchTier.WEAK_MATCH, MatchTier.STRONG_MATCH}:
            payload["zone_answer"] = answer_with_context(request.query, result.matches)

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        payload["latency_ms"] = elapsed_ms
        logger.info("POST /query completed in %.1f ms", elapsed_ms)
        return payload
    except Exception:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        logger.exception("POST /query failed after %.1f ms", elapsed_ms)
        raise


if __name__ == "__main__":
    # Railway (and most PaaS) inject the port to bind via $PORT at runtime; never
    # hardcode it. The Procfile runs uvicorn directly with --port $PORT; this block
    # makes `python -m api.server` honor the same env var as a fallback entrypoint.
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
