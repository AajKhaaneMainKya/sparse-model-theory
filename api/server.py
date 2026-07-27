from __future__ import annotations

from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
import logging
from pathlib import Path
import time
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from engine.gate import route_note
from engine.note import Note, NoteValidationError, load_note, load_notes, parse_frontmatter
from engine.retrieval import MatchResult, MatchTier, precedent_matches

from .zone import answer_with_context


ROOT = Path(__file__).resolve().parents[1]
NOTES_DIR = ROOT / "notes"
EXAMPLES_DIR = ROOT / "examples"


app = FastAPI(title="Sparse Model Theory API")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://localhost(:[0-9]+)?$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["content-type"],
)


@dataclass(frozen=True)
class QueryRouteSubject:
    anchor_type: str


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    anchor_type: Literal["fixed", "contested"]
    notes_source: Literal["notes", "examples"] = "notes"


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


@app.post("/query")
def query(request: QueryRequest) -> dict[str, object]:
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
