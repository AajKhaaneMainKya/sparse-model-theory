from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    ".pytest_cache",
    "__pycache__",
    "api",
    "engine",
    "logs",
    "notes",
    "daily",
    "private",
    "internal",
    "raw_uploads",
    "tests",
    "uploads",
}
EXCLUDED_FILENAME_PREFIXES = (".env",)
SECTION_HEADINGS = {
    "ai projects": "Projects",
    "ai projects and community": "Projects",
    "achievements": "Achievements",
    "education": "Education",
    "work experience": "Experience",
    "experience": "Experience",
    "projects": "Projects",
    "projects and community": "Projects",
    "products": "Projects",
    "skills": "Skills",
    "certifications": "Certifications",
    "awards": "Awards",
    "publications": "Publications",
    "contact": "Contact",
    "summary": "Summary",
    "community": "Community",
}
INTENT_TERMS = {
    "education": {"mba", "degree", "education", "college", "university", "institute", "school", "study", "studied"},
    "work": {"worked", "work", "role", "company", "experience", "employer", "where"},
    "projects": {"built", "build", "project", "projects", "shipped", "agentic", "openai", "fastapi", "products"},
    "skills": {"skills", "tools", "stack", "technologies"},
    "proof": {"evidence", "proof", "demonstrate", "examples"},
    "fit": {"role", "roles", "fit", "founder", "recruiter", "interview"},
    "contact": {"contact", "email", "linkedin", "phone"},
    "location": {"location", "located", "based", "city", "where"},
}
INTENT_SECTIONS = {
    "education": {"education"},
    "work": {"experience"},
    "projects": {"projects"},
    "skills": {"skills"},
    "proof": {"summary", "projects", "experience"},
    "fit": {"summary", "experience", "skills"},
    "contact": {"summary", "contact"},
    "location": {"summary", "contact"},
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
CONTAMINATED_RESUME_PATTERNS = {
    "section-retrieval-test",
    "ingestion-verification",
    "verification-resume",
    "test-fixture",
    "tmp",
    "temp",
}
RESUME_FACTS_DIRNAME = "_facts"
RESUME_FACT_SCHEMA_VERSION = 1
RESUME_FACT_CATEGORIES = {
    "identity",
    "contact",
    "location",
    "links",
    "summary",
    "education",
    "work_experience",
    "projects",
    "skills",
    "tools",
    "domains",
    "achievements",
    "metrics",
    "communities",
    "dates",
    "roles",
    "organizations",
}
RESUME_FACT_CATEGORY_ALIASES = {
    "achievement": "achievements",
    "achievements": "achievements",
    "community": "communities",
    "communities": "communities",
    "project": "projects",
    "projects": "projects",
    "skills": "skills",
    "work": "work_experience",
    "work_experience": "work_experience",
}
PROMPT_INJECTION_PATTERNS = [
    r"ignore (?:all )?(?:previous|prior) instructions",
    r"reveal .*?(?:private|secret|system|developer|prompt|notes|api key)",
    r"(?:system|developer) prompt",
    r"api[_ -]?key",
    r"private notes?",
    r"notes/daily",
    r"daily captures?",
]


class AskRahulRequest(BaseModel):
    question: str = Field(min_length=1)
    source_page: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None


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


@dataclass(frozen=True)
class ResumeFact:
    category: str
    label: str
    value: str
    source_title: str
    source_path: str
    section_heading: str
    excerpt: str
    id: str = ""
    confidence: str = "high"

    @property
    def source(self) -> str:
        return f"{self.source_path}#{_section_anchor(self.section_heading)}"

    def evidence(self, score: int = 100) -> PublicEvidence:
        return PublicEvidence(
            title=self.source_title,
            source=self.source,
            excerpt=self.excerpt,
            score=score,
        )


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
    if relative.name.startswith(EXCLUDED_FILENAME_PREFIXES):
        return None
    if path.suffix.lower() not in PUBLIC_EXTENSIONS:
        return None
    if relative.parts and relative.parts[0] == "resumes" and is_contaminated_resume_name(relative.name):
        return None
    return str(relative)


def is_contaminated_resume_name(filename: str) -> bool:
    stem = Path(filename).stem.lower()
    return any(pattern in stem for pattern in CONTAMINATED_RESUME_PATTERNS)


def _is_contaminated_resume_name(filename: str) -> bool:
    return is_contaminated_resume_name(filename)


def _canonical_heading(raw: str) -> str | None:
    cleaned = re.sub(r"[^a-z ]+", " ", raw.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return SECTION_HEADINGS.get(cleaned)


def _schema_category(category: str) -> str:
    return RESUME_FACT_CATEGORY_ALIASES.get(category, category)


def _fact_id(source_resume: str, category: str, value: str, index: int = 0) -> str:
    seed = f"{source_resume}|{category}|{value}|{index}"
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
    slug = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
    return f"{slug}-{digest}"


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
        elif line.isupper() and _canonical_heading(line.title()):
            lines.append(f"## {_canonical_heading(line.title())}")
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


def resume_documents(documents: list[PublicDocument]) -> list[PublicDocument]:
    return [
        doc
        for doc in documents
        if doc.source.startswith("resumes/") and not is_contaminated_resume_name(Path(doc.source).name)
    ]


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.strip(" •\t-")).strip()


def _section_lines(chunk: PublicChunk) -> list[str]:
    return [_clean_line(line) for line in chunk.chunk_text.splitlines() if _clean_line(line)]


def _bullet_blocks(chunk: PublicChunk) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw_line in chunk.chunk_text.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        starts_item = bool(re.match(r"^(?:[-*•]|\d+\.)\s+", stripped))
        cleaned = _clean_line(stripped)
        if starts_item and current:
            blocks.append(" ".join(current).strip())
            current = [cleaned]
        elif current:
            current.append(cleaned)
        else:
            current = [cleaned]
    if current:
        blocks.append(" ".join(current).strip())
    return blocks


def _date_range_pattern() -> str:
    month = (
        "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|"
        "January|February|March|April|May|June|July|August|September|October|November|December"
    )
    month_pattern = rf"(?:{month})"
    return rf"{month_pattern}\s+\d{{4}}\s*(?:--|-|to)\s*(?:{month_pattern}\s+\d{{4}}|\d{{4}}|Present|present)"


def _looks_like_org_date_line(line: str) -> bool:
    return bool(re.search(_date_range_pattern(), line))


def _org_from_date_line(line: str) -> str:
    return re.sub(_date_range_pattern(), "", line, flags=re.IGNORECASE).strip(" ,-")


def _date_from_line(line: str) -> str:
    match = re.search(_date_range_pattern(), line, flags=re.IGNORECASE)
    return match.group(0).strip() if match else ""


def _dedupe_facts(facts: list[ResumeFact]) -> list[ResumeFact]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[ResumeFact] = []
    for fact in facts:
        key = (_schema_category(fact.category), fact.label.lower(), re.sub(r"\s+", " ", fact.value.lower()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def extract_resume_facts(documents: list[PublicDocument]) -> list[ResumeFact]:
    json_facts = load_resume_fact_files()
    facts: list[ResumeFact] = list(json_facts)
    json_sources = {fact.source_path for fact in json_facts}
    for doc in resume_documents(documents):
        if doc.source in json_sources:
            continue
        for chunk in chunk_public_document(doc):
            section = chunk.section_heading.lower()
            if section == "summary":
                facts.extend(_extract_summary_contact_facts(chunk))
            elif section == "education":
                facts.extend(_extract_education_facts(chunk))
            elif section == "experience":
                facts.extend(_extract_work_facts(chunk))
            elif section in {"projects", "community", "achievements"}:
                facts.extend(_extract_project_achievement_facts(chunk))
            elif section == "skills":
                facts.extend(_extract_skill_facts(chunk))
    return _dedupe_facts(facts)


def load_resume_fact_files(corpus_dir: Path | None = None) -> list[ResumeFact]:
    root = corpus_dir or PUBLIC_CORPUS_DIR
    facts_dir = root / "resumes" / RESUME_FACTS_DIRNAME
    if not facts_dir.exists():
        return []

    facts: list[ResumeFact] = []
    for path in sorted(facts_dir.glob("*.json")):
        if is_contaminated_resume_name(path.name):
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        source_resume = str(data.get("source_resume") or "")
        if not source_resume.startswith("resumes/") or source_resume.startswith(f"resumes/{RESUME_FACTS_DIRNAME}/"):
            continue
        if is_contaminated_resume_name(Path(source_resume).name):
            continue
        for item in data.get("facts", []):
            if not isinstance(item, dict):
                continue
            category = str(item.get("category") or "")
            if category not in RESUME_FACT_CATEGORIES:
                continue
            value = str(item.get("value") or "").strip()
            evidence = str(item.get("evidence_text") or value).strip()
            section = str(item.get("source_section") or "Summary").strip() or "Summary"
            confidence = str(item.get("confidence") or "medium")
            if confidence not in {"high", "medium", "low"}:
                confidence = "medium"
            if not value or not evidence:
                continue
            facts.append(
                ResumeFact(
                    category=category,
                    label=category,
                    value=value,
                    source_title=Path(source_resume).stem.replace("-", " ").title(),
                    source_path=source_resume,
                    section_heading=section,
                    excerpt=evidence,
                    id=str(item.get("id") or _fact_id(source_resume, category, value)),
                    confidence=confidence,
                )
            )
    return _dedupe_facts(facts)


def build_resume_fact_artifact(
    *,
    source_resume: str,
    source_title: str,
    markdown_text: str,
) -> dict[str, object]:
    doc = PublicDocument(
        title=source_title,
        source=source_resume,
        text=normalize_public_text(markdown_text),
    )
    raw_facts = extract_resume_facts_from_documents([doc])
    expanded = _expand_resume_contract_facts(raw_facts, doc)
    deduped = _dedupe_facts(expanded)
    payload_facts = [_resume_fact_payload(fact, index) for index, fact in enumerate(deduped, start=1)]
    warnings = _resume_fact_warnings(payload_facts)
    return {
        "schema_version": RESUME_FACT_SCHEMA_VERSION,
        "source_resume": source_resume,
        "source_title": source_title,
        "facts": payload_facts,
        "warnings": warnings,
    }


def extract_resume_facts_from_documents(documents: list[PublicDocument]) -> list[ResumeFact]:
    facts: list[ResumeFact] = []
    for doc in resume_documents(documents):
        for chunk in chunk_public_document(doc):
            section = chunk.section_heading.lower()
            if section == "summary":
                facts.extend(_extract_summary_contact_facts(chunk))
            elif section == "education":
                facts.extend(_extract_education_facts(chunk))
            elif section == "experience":
                facts.extend(_extract_work_facts(chunk))
            elif section in {"projects", "community", "achievements"}:
                facts.extend(_extract_project_achievement_facts(chunk))
            elif section == "skills":
                facts.extend(_extract_skill_facts(chunk))
    return _dedupe_facts(facts)


def _expand_resume_contract_facts(facts: list[ResumeFact], doc: PublicDocument) -> list[ResumeFact]:
    expanded: list[ResumeFact] = []
    identity = _resume_identity_fact(doc)
    if identity:
        expanded.append(identity)

    for fact in facts:
        category = _schema_category(fact.category)
        expanded.append(_replace_fact_category(fact, category, confidence=fact.confidence))
        expanded.extend(_derived_facts_from_resume_fact(fact, category))

    return _dedupe_facts(expanded)


def _resume_identity_fact(doc: PublicDocument) -> ResumeFact | None:
    for line in doc.text.splitlines():
        cleaned = _clean_line(line)
        if cleaned.lower() == "rahul shiv shankar":
            return ResumeFact(
                category="identity",
                label="name",
                value=cleaned,
                source_title=doc.title,
                source_path=doc.source,
                section_heading="Summary",
                excerpt=cleaned,
                confidence="high",
            )
    if "rahul shiv shankar" in doc.title.lower():
        return ResumeFact(
            category="identity",
            label="name",
            value="Rahul Shiv Shankar",
            source_title=doc.title,
            source_path=doc.source,
            section_heading="Summary",
            excerpt=doc.title,
            confidence="medium",
        )
    return None


def _replace_fact_category(fact: ResumeFact, category: str, confidence: str = "high") -> ResumeFact:
    return ResumeFact(
        category=category,
        label=fact.label,
        value=fact.value,
        source_title=fact.source_title,
        source_path=fact.source_path,
        section_heading=fact.section_heading,
        excerpt=fact.excerpt,
        id=fact.id,
        confidence=confidence,
    )


def _derived_facts_from_resume_fact(fact: ResumeFact, category: str) -> list[ResumeFact]:
    derived: list[ResumeFact] = []
    text = fact.excerpt or fact.value

    if category == "work_experience":
        match = re.match(r"^(.*?)\s+\((.*?)\)(?:\s+—\s+(.*))?$", fact.value)
        if match:
            org, dates, role = [item.strip() if item else "" for item in match.groups()]
            if org:
                derived.append(_derived_fact(fact, "organizations", org, "organization", "high"))
            if dates:
                derived.append(_derived_fact(fact, "dates", dates, "dates", "high"))
            if role:
                derived.append(_derived_fact(fact, "roles", role, "role", "high"))

    if category == "education":
        dates = _date_from_line(text) or _year_range_from_line(text)
        if dates:
            derived.append(_derived_fact(fact, "dates", dates, "dates", "medium"))
        first_line = text.splitlines()[0].strip() if text.splitlines() else ""
        if first_line and not re.search(r"\b(MBA|B\.?Tech|Bachelor|Master|Degree|Certified)\b", first_line, re.IGNORECASE):
            derived.append(_derived_fact(fact, "organizations", _strip_date_tail(first_line), "institution", "medium"))

    if category in {"projects", "work_experience", "summary", "achievements", "communities"}:
        for metric in _extract_metric_values(text):
            derived.append(_derived_fact(fact, "metrics", metric, "metric", "medium"))

    if category in {"contact", "summary", "projects"}:
        for link in _extract_links(text):
            derived.append(_derived_fact(fact, "links", link, "link", "high"))

    if category == "skills":
        label = fact.label.lower()
        for item in _split_skill_items(fact.value):
            if _looks_like_tool_skill(label, item):
                derived.append(_derived_fact(fact, "tools", item, "tool", "medium"))
            if _looks_like_domain_skill(label, item):
                derived.append(_derived_fact(fact, "domains", item, "domain", "medium"))

    return derived


def _derived_fact(
    source: ResumeFact,
    category: str,
    value: str,
    label: str,
    confidence: str,
) -> ResumeFact:
    return ResumeFact(
        category=category,
        label=label,
        value=value,
        source_title=source.source_title,
        source_path=source.source_path,
        section_heading=source.section_heading,
        excerpt=source.excerpt,
        confidence=confidence,
    )


def _year_range_from_line(text: str) -> str:
    match = re.search(r"\b\d{4}\s*(?:--|-|to)\s*(?:\d{4}|Present|present)\b", text)
    return match.group(0) if match else ""


def _extract_metric_values(text: str) -> list[str]:
    patterns = [
        r"\b\d+\+?\s*(?:years|participants|programs|product lines|member sales team|clients|months)\b",
        r"\b\d+\+",
        r"\b\d+(?:\.\d+)?%",
        r"\b(?:CPL|ROAS|P&L|0-1)\b",
    ]
    metrics: list[str] = []
    for pattern in patterns:
        metrics.extend(match.group(0).strip() for match in re.finditer(pattern, text, flags=re.IGNORECASE))
    return list(dict.fromkeys(metrics))


def _extract_links(text: str) -> list[str]:
    links = re.findall(r"(?:https?://)?(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/[^\s,)]*)?", text, flags=re.IGNORECASE)
    return [link.strip(".,)") for link in links if not link.lower().endswith(".pdf")]


def _split_skill_items(value: str) -> list[str]:
    _, _, remainder = value.partition(":")
    text = remainder or value
    return [item.strip() for item in re.split(r",|\|", text) if item.strip()]


def _looks_like_tool_skill(label: str, item: str) -> bool:
    lowered = f"{label} {item}".lower()
    return any(token in lowered for token in ("technical", "api", "python", "fastapi", "redis", "claude", "phi", "sql", "salesforce"))


def _looks_like_domain_skill(label: str, item: str) -> bool:
    lowered = f"{label} {item}".lower()
    return any(token in lowered for token in ("growth", "gtm", "commercial", "product", "strategy", "ops", "semiconductor", "bfsi"))


def _resume_fact_payload(fact: ResumeFact, index: int) -> dict[str, str]:
    category = _schema_category(fact.category)
    return {
        "id": fact.id or _fact_id(fact.source_path, category, fact.value, index),
        "category": category,
        "value": fact.value,
        "source_resume": fact.source_path,
        "source_section": fact.section_heading,
        "evidence_text": fact.excerpt,
        "confidence": fact.confidence if fact.confidence in {"high", "medium", "low"} else "medium",
    }


def _resume_fact_warnings(facts: list[dict[str, str]]) -> list[str]:
    categories = {fact["category"] for fact in facts}
    warnings: list[str] = []
    required_sections = {
        "summary": "summary/headline",
        "education": "education",
        "work_experience": "work experience",
        "projects": "projects/products",
        "skills": "skills",
    }
    for category, label in required_sections.items():
        if category not in categories:
            warnings.append(f"Low confidence extraction: missing {label} facts.")
    if not facts:
        warnings.append("No structured facts were extracted from the resume.")
    return warnings


def _extract_summary_contact_facts(chunk: PublicChunk) -> list[ResumeFact]:
    lines = _section_lines(chunk)
    facts: list[ResumeFact] = []
    metadata_prefixes = ("source:", "original filename:", "updated:")
    summary_lines = [
        line
        for line in lines
        if "@" not in line
        and "linkedin.com" not in line
        and line.lower() != "rahul shiv shankar"
        and not line.lower().startswith(metadata_prefixes)
    ]
    summary_text = " ".join(summary_lines)
    for line in lines:
        if "@" in line or "linkedin.com" in line or re.search(r"\+\d", line):
            parts = [part.strip() for part in re.split(r"\s+\|\s+", line) if part.strip()]
            for part in parts:
                lowered = part.lower()
                if "@" in part:
                    facts.append(_fact(chunk, "contact", "email", part))
                elif "linkedin.com" in lowered:
                    facts.append(_fact(chunk, "contact", "linkedin", part))
                elif re.search(r"\+\d", part):
                    facts.append(_fact(chunk, "contact", "phone", part))
                elif "," in part:
                    facts.append(_fact(chunk, "location", "location", part))
    if summary_text and any(token in summary_text.lower() for token in ("years across", "work best", "strongest")):
        facts.append(_fact(chunk, "summary", "summary", summary_text))
    if summary_text and any(token in summary_text.lower() for token in ("buildathon", "growthx", "newsletter")):
        facts.append(_fact(chunk, "community", "community", summary_text))
    return facts


def _extract_education_facts(chunk: PublicChunk) -> list[ResumeFact]:
    lines = _section_lines(chunk)
    facts: list[ResumeFact] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        if re.search(r"\b(MBA|B\.?Tech|Bachelor|Master|Degree)\b", line, flags=re.IGNORECASE):
            facts.append(_fact(chunk, "education", "education", line))
            index += 1
            continue
        if next_line and re.search(r"\b(MBA|B\.?Tech|Bachelor|Master|Degree)\b", next_line, flags=re.IGNORECASE):
            value = f"{line}\n{next_line}"
            facts.append(_fact(chunk, "education", "education", value))
            index += 2
            continue
        if "certified" in line.lower():
            facts.append(_fact(chunk, "education", "certification", line))
        index += 1
    return facts


def _extract_work_facts(chunk: PublicChunk) -> list[ResumeFact]:
    lines = _section_lines(chunk)
    facts: list[ResumeFact] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _looks_like_org_date_line(line):
            index += 1
            continue
        org = _org_from_date_line(line)
        dates = _date_from_line(line)
        title = lines[index + 1] if index + 1 < len(lines) and not lines[index + 1].startswith("•") else ""
        bullets: list[str] = []
        cursor = index + 2 if title else index + 1
        while cursor < len(lines) and not _looks_like_org_date_line(lines[cursor]):
            bullets.append(lines[cursor])
            cursor += 1
        excerpt_lines = [line]
        if title:
            excerpt_lines.append(title)
        excerpt_lines.extend(bullets[:3])
        label = org or line
        value = f"{org} ({dates})"
        if title:
            value += f" — {title}"
        facts.append(_fact(chunk, "work", label, value, "\n".join(excerpt_lines)))
        for bullet in bullets:
            if any(marker in bullet.lower() for marker in ("owned", "built", "managed", "led", "launched", "participants", "40+", "5+", "0-1")):
                facts.append(_fact(chunk, "achievement", label, bullet))
        index = cursor
    return facts


def _extract_project_achievement_facts(chunk: PublicChunk) -> list[ResumeFact]:
    facts: list[ResumeFact] = []
    for line in _bullet_blocks(chunk):
        if not line:
            continue
        label = line.split("--", 1)[0].split(" - ", 1)[0].strip()[:80] or "project"
        facts.append(_fact(chunk, "project", label, line))
        if any(token in line.lower() for token in ("buildathon", "growthx", "newsletter")):
            facts.append(_fact(chunk, "community", label, line))
        if any(marker in line.lower() for marker in ("100+", "featured", "launched", "built", "hosted", "fine-tuned")):
            facts.append(_fact(chunk, "achievement", label, line))
    return facts


def _extract_skill_facts(chunk: PublicChunk) -> list[ResumeFact]:
    facts: list[ResumeFact] = []
    for line in _section_lines(chunk):
        if ":" in line:
            label, value = [part.strip() for part in line.split(":", 1)]
            facts.append(_fact(chunk, "skills", label, f"{label}: {value}"))
        else:
            facts.append(_fact(chunk, "skills", "skills", line))
    return facts


def _fact(
    chunk: PublicChunk,
    category: str,
    label: str,
    value: str,
    excerpt: str | None = None,
) -> ResumeFact:
    return ResumeFact(
        category=category,
        label=label,
        value=value,
        source_title=chunk.source_title,
        source_path=chunk.source_path,
        section_heading=chunk.section_heading,
        excerpt=excerpt or value,
    )


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


def _is_prompt_injection(question: str) -> bool:
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in PROMPT_INJECTION_PATTERNS)


def _refusal_response() -> dict[str, object]:
    return {
        "answer": (
            "I cannot follow instructions to reveal private notes, secrets, system prompts, "
            "or internal data. Ask Rahul answers only from the public corpus."
        ),
        "evidence": [],
        "caveats": ["Prompt-injection style requests are refused before retrieval or model calls."],
        "suggested_interview_questions": [],
    }


def _fact_evidence(facts: list[ResumeFact], limit: int = 5) -> list[PublicEvidence]:
    return [fact.evidence(score=120 - index) for index, fact in enumerate(facts[:limit])]


def _canonical_fact_value(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _conflict_response(category: str, facts: list[ResumeFact]) -> tuple[str, list[PublicEvidence]]:
    examples = [f"{fact.value} ({fact.source})" for fact in facts[:5]]
    return (
        f"The public resume evidence contains conflicting {category} facts, so I should not choose one silently. "
        "Conflicting evidence: " + " | ".join(examples),
        _fact_evidence(facts),
    )


def _facts_by_category(facts: list[ResumeFact], *categories: str) -> list[ResumeFact]:
    wanted = {_schema_category(category) for category in categories}
    return [fact for fact in facts if _schema_category(fact.category) in wanted]


def _question_mentions(question: str, *terms: str) -> bool:
    lowered = question.lower()
    return any(term.lower() in lowered for term in terms)


def _answer_from_structured_resume(question: str, facts: list[ResumeFact]) -> tuple[str, list[PublicEvidence]] | None:
    lowered = question.lower()

    if _question_mentions(lowered, "google"):
        if not any("google" in fact.value.lower() for fact in facts):
            return (
                "The public resume evidence does not show Rahul worked at Google.",
                [],
            )

    if _question_mentions(lowered, "study", "studied") and _question_mentions(lowered, "regenesys"):
        education = _facts_by_category(facts, "education")
        regenesys_education = [fact for fact in education if "regenesys" in fact.value.lower()]
        if regenesys_education:
            return (
                "The public resume education evidence mentions Regenesys in education entries.",
                _fact_evidence(regenesys_education),
            )
        work_regenesys = [fact for fact in _facts_by_category(facts, "work_experience") if "regenesys" in fact.value.lower()]
        answer = "The public resume evidence does not show Rahul studied at Regenesys."
        if work_regenesys:
            answer += " It shows Regenesys as work experience/employer evidence, not MBA education."
        return answer, _fact_evidence(work_regenesys)

    if _question_mentions(lowered, "mba"):
        answer = _education_answer_from_facts(question, facts)
        if answer:
            return answer

    if _question_mentions(lowered, "education", "degree", "college", "university", "school") and not _question_mentions(lowered, "work"):
        education = _facts_by_category(facts, "education")
        if not education:
            return None
        grouped = _group_compatible_facts(education)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume education evidence includes:\n" + "\n".join(lines), _fact_evidence(education)

    if _question_mentions(lowered, "where has", "worked", "work experience", "employer", "company"):
        work = _facts_by_category(facts, "work_experience")
        if not work:
            return (
                "The public resume evidence does not contain work experience entries.",
                [],
            )
        grouped = _group_compatible_facts(work)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume work experience includes:\n" + "\n".join(lines), _fact_evidence(work)

    if _question_mentions(lowered, "role", "roles", "strongest", "fit", "recruiter"):
        fit_facts = _facts_by_category(facts, "summary", "work_experience", "skills", "achievements")
        if not fit_facts:
            return None
        summary = _facts_by_category(fit_facts, "summary")
        skills = _facts_by_category(fit_facts, "skills")
        work = _facts_by_category(fit_facts, "work_experience")
        achievements = _facts_by_category(fit_facts, "achievements")
        lines: list[str] = []
        if summary:
            lines.append(f"- Positioning: {summary[0].value}")
        if work:
            lines.append("- Relevant roles: " + "; ".join(item.value for item in work[:4]))
        if skills:
            lines.append("- Skills/tools: " + "; ".join(item.value for item in skills[:3]))
        if achievements:
            lines.append("- Proof points: " + "; ".join(item.value for item in achievements[:3]))
        return (
            "Based on public resume evidence, Rahul is strongest for AI product, growth/GTM product, "
            "and technical product roles where ownership connects product, systems, and revenue.\n"
            + "\n".join(lines),
            _fact_evidence(fit_facts, limit=7),
        )

    if _question_mentions(lowered, "agentic systems", "openclaw", "sparse model", "fastapi") and not _question_mentions(lowered, "resume"):
        return None

    if _question_mentions(lowered, "built", "build", "projects", "products", "shipped"):
        projects = _facts_by_category(facts, "projects", "communities")
        if not projects:
            return None
        grouped = _group_compatible_facts(projects)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume/project evidence includes:\n" + "\n".join(lines[:8]), _fact_evidence(projects)

    if _question_mentions(lowered, "skills", "tools", "stack", "technologies"):
        skills = _facts_by_category(facts, "skills")
        if not skills:
            return None
        grouped = _group_compatible_facts(skills)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume skills evidence includes:\n" + "\n".join(lines), _fact_evidence(skills)

    if _question_mentions(lowered, "contact", "email", "linkedin", "phone", "location", "where is rahul based", "based in"):
        contact = _facts_by_category(facts, "contact", "location")
        if not contact:
            return None
        grouped = _group_compatible_facts(contact)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume contact/location evidence includes:\n" + "\n".join(lines), _fact_evidence(contact)

    if _question_mentions(lowered, "achievements", "metrics", "proof", "newsletter", "buildathons", "community"):
        achievements = _facts_by_category(facts, "achievements", "communities")
        if not achievements:
            return None
        grouped = _group_compatible_facts(achievements)
        lines = [f"- {items[0].value}" for items in grouped.values()]
        return "Rahul's public resume achievement/community evidence includes:\n" + "\n".join(lines[:8]), _fact_evidence(achievements)

    return None


def _group_compatible_facts(facts: list[ResumeFact]) -> dict[str, list[ResumeFact]]:
    grouped: dict[str, list[ResumeFact]] = {}
    for fact in facts:
        grouped.setdefault(_canonical_fact_value(fact.value), []).append(fact)
    return grouped


def _education_answer_from_facts(question: str, facts: list[ResumeFact]) -> tuple[str, list[PublicEvidence]] | None:
    terms = _tokens(question)
    if not (terms & INTENT_TERMS["education"]):
        return None

    education = _facts_by_category(facts, "education")
    candidates: dict[str, list[ResumeFact]] = {}
    for fact in education:
        candidate = _extract_mba_institution(fact.excerpt)
        if candidate:
            candidates.setdefault(_canonical_institution(candidate), []).append(fact)

    if not candidates:
        return None

    flattened = [item for group in candidates.values() for item in group]
    if len(candidates) > 1:
        return _conflict_response("MBA institution", flattened)

    supporting_items = next(iter(candidates.values()))
    extracted = _extract_mba_institution(supporting_items[0].excerpt)
    if not extracted:
        return None
    return (
        f"The public resume evidence indicates Rahul completed his MBA at {extracted}. "
        f"The supporting evidence is in {supporting_items[0].source}.",
        _fact_evidence(supporting_items),
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
    if _is_prompt_injection(question):
        return _refusal_response()

    documents = load_public_documents()
    caveats = _corpus_caveats(documents)
    resume_facts = extract_resume_facts(documents)
    structured_answer = _answer_from_structured_resume(question, resume_facts)

    if structured_answer is not None:
        answer, structured_evidence = structured_answer
        return {
            "answer": answer,
            "evidence": [item.payload() for item in structured_evidence],
            "caveats": caveats,
            "suggested_interview_questions": _fallback_interview_questions(structured_evidence),
        }

    evidence = retrieve_public_evidence(question, documents)
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
