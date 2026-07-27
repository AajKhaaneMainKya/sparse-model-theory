from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
import yaml


VALID_ANCHOR_TYPES = {"fixed", "contested"}
VALID_CLUSTERS = {
    "kill-decisively",
    "distribution-over-quality",
    "personal-pain-wins",
    "uncategorized",
}
VALID_CONFIDENCE = {"high", "medium", "low"}
REQUIRED_FIELDS = {
    "id",
    "title",
    "anchor_type",
    "cluster",
    "domain",
    "sequence",
    "created_at",
    "source",
    "confidence",
}


class NoteValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Note:
    path: Path
    metadata: dict[str, Any]
    body: str

    @property
    def id(self) -> str:
        return str(self.metadata["id"])

    @property
    def title(self) -> str:
        return str(self.metadata["title"])

    @property
    def anchor_type(self) -> str:
        return str(self.metadata["anchor_type"])

    @property
    def cluster(self) -> str:
        return str(self.metadata["cluster"])


def load_notes(root: Path) -> list[Note]:
    if not root.exists():
        raise FileNotFoundError(f"Notes path does not exist: {root}")

    files = sorted(root.rglob("*.md")) if root.is_dir() else [root]
    notes = [load_note(path) for path in files]
    return notes


def load_note(path: Path) -> Note:
    text = path.read_text(encoding="utf-8")
    metadata, body = parse_frontmatter(text, path)
    note = Note(path=path, metadata=metadata, body=body.strip())
    validate_note(note)
    return note


def parse_frontmatter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise NoteValidationError(f"{path}: missing YAML frontmatter")

    try:
        _, raw_yaml, body = text.split("---\n", 2)
    except ValueError as exc:
        raise NoteValidationError(f"{path}: malformed frontmatter fence") from exc

    metadata = parse_simple_yaml(raw_yaml, path)
    return metadata, body


def parse_simple_yaml(raw: str, path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise NoteValidationError(f"{path}: malformed YAML frontmatter") from exc

    if not isinstance(data, dict):
        raise NoteValidationError(f"{path}: YAML frontmatter must be a mapping")

    return data


def validate_note(note: Note) -> None:
    missing = REQUIRED_FIELDS - set(note.metadata)
    if missing:
        raise NoteValidationError(f"{note.path}: missing required fields: {sorted(missing)}")

    if note.anchor_type not in VALID_ANCHOR_TYPES:
        raise NoteValidationError(f"{note.path}: invalid anchor_type: {note.anchor_type}")

    if note.cluster not in VALID_CLUSTERS:
        raise NoteValidationError(f"{note.path}: invalid cluster: {note.cluster}")

    domains = note.metadata["domain"]
    if not isinstance(domains, list) or not domains:
        raise NoteValidationError(f"{note.path}: domain must be a non-empty list")

    sequence = note.metadata["sequence"]
    if not isinstance(sequence, list):
        raise NoteValidationError(f"{note.path}: sequence must be a list")

    if note.metadata["confidence"] not in VALID_CONFIDENCE:
        raise NoteValidationError(f"{note.path}: invalid confidence: {note.metadata['confidence']}")

    try:
        date.fromisoformat(str(note.metadata["created_at"]))
    except ValueError as exc:
        raise NoteValidationError(f"{note.path}: created_at must be YYYY-MM-DD") from exc
