from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re

from pydantic import BaseModel, Field

from .zone import _call_openai_model


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_CORPUS_DIR = ROOT / "public_corpus"
PUBLIC_SYSTEM_PROMPT = (
    "You answer questions about Rahul's work and fit using only the provided public corpus excerpts. "
    "If the corpus does not support a claim, say that evidence is missing. Be specific, "
    "recruiter-friendly, and honest. Include evidence and caveats. Do not mention private notes or "
    "internal daily captures unless explaining that they are excluded."
)
ASK_RAHUL_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "suggested_interview_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "caveats", "suggested_interview_questions"],
    "additionalProperties": False,
}

STOPWORDS = {
    "a",
    "about",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "built",
    "can",
    "did",
    "do",
    "does",
    "exists",
    "fit",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "his",
    "i",
    "in",
    "is",
    "it",
    "its",
    "my",
    "of",
    "on",
    "or",
    "our",
    "rahul",
    "should",
    "that",
    "the",
    "their",
    "through",
    "to",
    "what",
    "where",
    "with",
    "worked",
    "your",
}
WEAK_PHRASE_TOKENS = STOPWORDS | {"complete", "completed"}
PUBLIC_EXTENSIONS = {".md", ".txt"}
EXCLUDED_PATH_PARTS = {
    ".git",
    ".venv",
    "logs",
    "notes",
    "daily",
    "private",
    "internal",
}
SECTION_HEADINGS = {
    "education": "Education",
    "work experience": "Experience",
    "experience": "Experience",
    "projects": "Projects",
    "skills": "Skills",
    "certifications": "Certifications",
    "awards": "Awards",
    "publications": "Publications",
    "contact": "Contact",
    "summary": "Summary",
}
INTENT_TERMS = {
    "education": {"mba", "degree", "education", "college", "university", "institute", "school"},
    "work": {"worked", "work", "role", "company", "experience", "employer"},
    "projects": {"built", "build", "project", "projects", "shipped", "agentic", "openai", "fastapi"},
    "skills": {"skills", "tools", "stack", "technologies"},
    "proof": {"evidence", "proof", "demonstrate", "examples"},
    "fit": {"role", "roles", "fit", "founder", "recruiter", "interview"},
}
INTENT_SECTIONS = {
    "education": {"education"},
    "work": {"experience"},
    "projects": {"projects"},
    "skills": {"skills"},
    "proof": {"summary", "projects", "experience"},
    "fit": {"summary", "experience", "skills"},
}
ENTITY_TERMS = {
    "mba",
    "regenesys",
    "pwc",
    "akshar",
    "sahayak",
    "growthx",
    "openai",
    "fastapi",
    "openclaw",
}
MAX_CHUNK_CHARS = 1600
CHUNK_OVERLAP_CHARS = 220


class AskRahulRequest(BaseModel):
    question: str = Field(min_length=1)


@dataclass(frozen=True)
class PublicDocument:
    title: str
    source: str
    text: str


@dataclass(frozen=True)
class PublicChunk:
    source_path: str
    source_title: str
    section_heading: str
    chunk_text: str
    chunk_id: str


@dataclass(frozen=True)
class PublicEvidence:
    title: str
    source: str
    excerpt: str
    score: int

    def payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "source": self.source,
            "excerpt": self.excerpt,
        }


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+-]*", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    }


def _ordered_tokens(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9][a-z0-9+-]*", text.lower())
        if len(token) > 1 and token not in STOPWORDS
    ]


def _raw_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9+-]*", text.lower())


def _title_from_markdown(path: Path, text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line.removeprefix("# ").strip()
    return path.stem.replace("-", " ").title()


def _safe_source_path(path: Path, root: Path) -> str | None:
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        relative = resolved.relative_to(root_resolved)
    except ValueError:
        return None

    parts = set(relative.parts)
    if parts & EXCLUDED_PATH_PARTS:
        return None
    if path.suffix.lower() not in PUBLIC_EXTENSIONS:
        return None
    return str(relative)


def _canonical_heading(raw: str) -> str | None:
    cleaned = re.sub(r"[^a-z ]+", " ", raw.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return SECTION_HEADINGS.get(cleaned)


def _heading_regex() -> str:
    return "|".join(re.escape(item) for item in sorted(SECTION_HEADINGS, key=len, reverse=True))


def normalize_public_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)

    heading_pattern = _heading_regex()
    # Split common one-paragraph resume extractions where headings appear inline.
    normalized = re.sub(
        rf"(?<![#\w])({heading_pattern})\s*:\s*",
        lambda match: f"\n\n## {_canonical_heading(match.group(1)) or match.group(1).strip().title()}\n",
        normalized,
        flags=re.IGNORECASE,
    )

    lines: list[str] = []
    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue

        markdown_heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if markdown_heading:
            hashes, heading = markdown_heading.groups()
            canonical = _canonical_heading(heading) or heading.strip()
            lines.append(f"{hashes} {canonical}")
            continue

        canonical = _canonical_heading(line.rstrip(":"))
        if canonical:
            lines.append(f"## {canonical}")
        else:
            lines.append(line)

    return "\n".join(lines).strip()


def load_public_documents(corpus_dir: Path | None = None) -> list[PublicDocument]:
    root = corpus_dir or PUBLIC_CORPUS_DIR
    if not root.exists():
        return []

    documents: list[PublicDocument] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        source = _safe_source_path(path, root)
        if source is None:
            continue
        text = normalize_public_text(path.read_text(encoding="utf-8"))
        documents.append(
            PublicDocument(
                title=_title_from_markdown(path, text),
                source=source,
                text=text.strip(),
            )
        )
    return documents


def _section_anchor(heading: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 -]+", "", heading).strip()
    return re.sub(r"\s+", "-", cleaned) or "Summary"


def _chunk_windows(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        if end < len(text):
            boundary = text.rfind("\n", start, end)
            if boundary > start + 400:
                end = boundary
        windows.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(0, end - CHUNK_OVERLAP_CHARS)
    return [window for window in windows if window]


def chunk_public_document(doc: PublicDocument) -> list[PublicChunk]:
    chunks: list[PublicChunk] = []
    current_heading = "Summary"
    current_lines: list[str] = []
    current_index = 0
    saw_body = False

    def flush() -> None:
        nonlocal current_index, current_lines
        body = "\n".join(current_lines).strip()
        current_lines = []
        if not body:
            return
        for window_index, window in enumerate(_chunk_windows(body), start=1):
            suffix = f"-{window_index}" if len(body) > MAX_CHUNK_CHARS else ""
            chunks.append(
                PublicChunk(
                    source_path=doc.source,
                    source_title=doc.title,
                    section_heading=current_heading,
                    chunk_text=window,
                    chunk_id=f"{doc.source}#{_section_anchor(current_heading)}-{current_index}{suffix}",
                )
            )
        current_index += 1

    for line in doc.text.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line.strip())
        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()
            if level == 1 and not saw_body:
                continue
            flush()
            current_heading = _canonical_heading(title) or title
            continue

        if line.strip():
            saw_body = True
        current_lines.append(line)

    flush()
    if not chunks and doc.text.strip():
        chunks.append(
            PublicChunk(
                source_path=doc.source,
                source_title=doc.title,
                section_heading="Summary",
                chunk_text=doc.text.strip(),
                chunk_id=f"{doc.source}#Summary-0",
            )
        )
    return chunks


def chunk_public_documents(documents: list[PublicDocument]) -> list[PublicChunk]:
    chunks: list[PublicChunk] = []
    for doc in documents:
        chunks.extend(chunk_public_document(doc))
    return chunks


def detect_query_intents(question: str) -> set[str]:
    terms = set(_ordered_tokens(question))
    return {intent for intent, words in INTENT_TERMS.items() if terms & words}


def _phrases(question: str) -> list[str]:
    tokens = _raw_tokens(question)
    phrases = []
    for size in (3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase_tokens = tokens[index:index + size]
            strong_count = sum(1 for token in phrase_tokens if token not in WEAK_PHRASE_TOKENS)
            if strong_count >= 2 or (size == 2 and strong_count == 2):
                phrases.append(" ".join(phrase_tokens))
    return phrases


def _best_excerpt(text: str, query_terms: set[str], max_chars: int = 520) -> str:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    if not paragraphs:
        return ""

    ranked = sorted(
        paragraphs,
        key=lambda paragraph: len(_tokens(paragraph) & query_terms),
        reverse=True,
    )
    excerpt = "\n".join(
        re.sub(r"[ \t]+", " ", line).strip()
        for line in ranked[0].splitlines()
    ).strip("# ").strip()
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[: max_chars - 1].rsplit(" ", 1)[0].rstrip() + "..."


def _score_chunk(chunk: PublicChunk, question: str, query_terms: set[str], intents: set[str]) -> int:
    chunk_text = f"{chunk.source_title}\n{chunk.section_heading}\n{chunk.chunk_text}"
    chunk_terms = _tokens(chunk_text)
    overlap = query_terms & chunk_terms
    if not overlap:
        return 0

    lower_text = chunk_text.lower()
    score = len(overlap) * 4
    score += sum(5 for phrase in _phrases(question) if phrase in lower_text)
    score += sum(8 for term in query_terms & ENTITY_TERMS if term in chunk_terms)

    section_key = chunk.section_heading.lower()
    for intent in intents:
        if section_key in INTENT_SECTIONS.get(intent, set()):
            score += 10

    if chunk.source_path.startswith("resumes/"):
        score += 2
    elif chunk.source_path.startswith("projects/"):
        score += 2
    if query_terms & _tokens(chunk.source_path):
        score += 1

    return score


def retrieve_public_evidence(
    question: str,
    documents: list[PublicDocument] | None = None,
    limit: int = 5,
) -> list[PublicEvidence]:
    docs = documents if documents is not None else load_public_documents()
    query_terms = _tokens(question)
    if not query_terms:
        return []

    scored: list[PublicEvidence] = []
    intents = detect_query_intents(question)
    for chunk in chunk_public_documents(docs):
        score = _score_chunk(chunk, question, query_terms, intents)
        if score <= 0:
            continue
        scored.append(
            PublicEvidence(
                title=chunk.source_title,
                source=f"{chunk.source_path}#{_section_anchor(chunk.section_heading)}",
                excerpt=_best_excerpt(chunk.chunk_text, query_terms),
                score=score,
            )
        )

    return sorted(scored, key=lambda item: (item.score, item.title), reverse=True)[:limit]


def _corpus_caveats(documents: list[PublicDocument]) -> list[str]:
    for doc in documents:
        if doc.source == "caveats.md":
            lines = [
                line.strip("- ").strip()
                for line in doc.text.splitlines()
                if line.strip().startswith("- ")
            ]
            return [line for line in lines if line][:4]
    return ["The public corpus is intentionally limited to sanitized portfolio evidence."]


def _fallback_answer(question: str, evidence: list[PublicEvidence]) -> str:
    if not evidence:
        return (
            "The public corpus does not contain evidence for that claim. "
            "A stronger answer would require adding sanitized public proof."
        )

    education_answer = _education_answer_from_evidence(question, evidence)
    if education_answer:
        return education_answer

    titles = ", ".join(item.title for item in evidence[:3])
    return (
        f"Based on the public corpus, the strongest relevant evidence is in {titles}. "
        "The excerpts support only the claims shown in the evidence list; anything beyond that is not established here."
    )


def _education_answer_from_evidence(question: str, evidence: list[PublicEvidence]) -> str | None:
    terms = _tokens(question)
    if not (terms & INTENT_TERMS["education"]):
        return None

    education_evidence = [item for item in evidence if "#Education" in item.source]
    candidates: dict[str, list[PublicEvidence]] = {}
    for item in education_evidence:
        candidate = _extract_mba_institution(item.excerpt)
        if candidate:
            candidates.setdefault(_canonical_institution(candidate), []).append(item)

    if not candidates:
        return None

    if len(candidates) > 1:
        options = [
            f"{items[0].excerpt} ({items[0].source})"
            for items in candidates.values()
        ]
        return (
            "The public resume evidence contains conflicting MBA institution candidates, "
            "so I should not choose one without cleanup. Conflicting evidence: "
            + " | ".join(options)
        )

    supporting_items = next(iter(candidates.values()))
    source = supporting_items[0].source
    extracted = _extract_mba_institution(supporting_items[0].excerpt)
    if not extracted:
        return None
    return (
        f"The public resume evidence indicates Rahul completed his MBA at {extracted}. "
        f"The supporting evidence is in {source}."
    )


def _canonical_institution(name: str) -> str:
    lowered = name.lower()
    if "bitsom" in lowered or "bits pilani school of management" in lowered:
        return "bitsom-bits-pilani-school-of-management"
    return re.sub(r"[^a-z0-9]+", " ", lowered).strip()


def _strip_date_tail(line: str) -> str:
    return re.sub(r"\s+\d{4}\s*(?:--|-|to)\s*(?:\d{4}|present)?\s*$", "", line, flags=re.IGNORECASE).strip(" ,-")


def _extract_mba_institution(excerpt: str) -> str | None:
    lines = [line.strip(" -") for line in excerpt.splitlines() if line.strip()]
    if len(lines) <= 1:
        lines = [line.strip(" -") for line in re.split(r"\s{2,}|(?<=\d{4})\s+(?=MBA\b)", excerpt) if line.strip()]

    for index, line in enumerate(lines):
        if not re.search(r"\b(MBA|Master of Business Administration)\b", line, flags=re.IGNORECASE):
            continue

        same_line_patterns = [
            r"(?i)\b(?:MBA|Master of Business Administration)\b[^.\n]*\b(?:at|from)\s+([A-Z][A-Za-z0-9&.,'() -]{2,120})",
            r"(?i)([A-Z][A-Za-z0-9&.,'() -]{2,120})[^.\n]*\b(?:MBA|Master of Business Administration)\b",
        ]
        for pattern in same_line_patterns:
            match = re.search(pattern, line)
            if match:
                candidate = match.group(1).strip(" .,-")
                if candidate.upper() not in {"MBA"}:
                    return _strip_date_tail(candidate)

        if index > 0:
            previous = lines[index - 1]
            if previous and not re.search(r"\b(B\.?Tech|Bachelor|Certified|Scrum)\b", previous, flags=re.IGNORECASE):
                return _strip_date_tail(previous)

    return None


def _fallback_interview_questions(evidence: list[PublicEvidence]) -> list[str]:
    if not evidence:
        return [
            "What public proof would you point to for this claim?",
            "Which shipped artifact best demonstrates the skill in question?",
            "What should be considered unknown from the current public portfolio?",
        ]

    questions = [
        "Walk me through the boundary between open-ended interface and bounded execution in this work.",
        "Where did retrieval, routing, or orchestration fail in early versions, and what changed?",
        "Which parts are production-ready versus prototype or research-grade?",
    ]
    if any("OpenAI" in item.excerpt or "FastAPI" in item.excerpt for item in evidence):
        questions.append("How did you choose between hosted OpenAI calls and local-model fallback behavior?")
    return questions[:4]


def _public_model_answer(question: str, evidence: list[PublicEvidence]) -> dict[str, object] | None:
    if not os.environ.get("OPENAI_API_KEY"):
        return None

    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-terra")
    context = "\n\n".join(
        f"Source: {item.source}\nTitle: {item.title}\nExcerpt: {item.excerpt}"
        for item in evidence
    )
    input_text = (
        f"Question:\n{question}\n\n"
        f"Public corpus excerpts:\n{context or '(no relevant excerpts found)'}\n\n"
        "Return JSON matching the schema. Keep the answer concise and evidence-bound."
    )
    text = _call_openai_model(
        PUBLIC_SYSTEM_PROMPT,
        input_text,
        model,
        json_schema=ASK_RAHUL_SCHEMA,
        schema_name="ask_rahul_answer",
    )
    if text.startswith("Zone unavailable:"):
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict) or not isinstance(data.get("answer"), str):
        return None
    return data


def ask_rahul(question: str) -> dict[str, object]:
    documents = load_public_documents()
    evidence = retrieve_public_evidence(question, documents)
    caveats = _corpus_caveats(documents)
    deterministic_answer = _education_answer_from_evidence(question, evidence)

    if deterministic_answer:
        answer = deterministic_answer
        suggested = _fallback_interview_questions(evidence)
    else:
        model_payload = _public_model_answer(question, evidence)

        if model_payload is None:
            answer = _fallback_answer(question, evidence)
            suggested = _fallback_interview_questions(evidence)
        else:
            answer = str(model_payload["answer"])
            model_caveats = model_payload.get("caveats")
            caveats = [
                item
                for item in (model_caveats if isinstance(model_caveats, list) else [])
                if isinstance(item, str) and item.strip()
            ] or caveats
            model_suggested = model_payload.get("suggested_interview_questions")
            suggested = [
                item
                for item in (model_suggested if isinstance(model_suggested, list) else [])
                if isinstance(item, str) and item.strip()
            ] or _fallback_interview_questions(evidence)

    if not evidence and "evidence" not in answer.lower():
        answer = f"{answer} Evidence is missing from the public corpus."

    return {
        "answer": answer,
        "evidence": [item.payload() for item in evidence],
        "caveats": caveats,
        "suggested_interview_questions": suggested,
    }
