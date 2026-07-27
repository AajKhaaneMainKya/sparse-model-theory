from __future__ import annotations

import argparse
from pathlib import Path

from .gate import route_note
from .note import load_notes
from .retrieval import precedent_matches


def main() -> None:
    parser = argparse.ArgumentParser(description="Sparse Model Theory local harness")
    subparsers = parser.add_subparsers(dest="command", required=True)

    route_parser = subparsers.add_parser("route", help="Route notes through the static gate")
    route_parser.add_argument("notes_path", type=Path)

    query_parser = subparsers.add_parser("query", help="Route a query and retrieve precedents")
    query_parser.add_argument("notes_path", type=Path)
    query_parser.add_argument("--anchor-type", choices=["fixed", "contested"], required=True)
    query_parser.add_argument("--text", required=True)
    query_parser.add_argument("--top-n", type=int, default=3)

    args = parser.parse_args()
    if args.command == "route":
        route(args.notes_path)
    elif args.command == "query":
        query(args.notes_path, args.anchor_type, args.text, args.top_n)


def route(notes_path: Path) -> None:
    for note in load_notes(notes_path):
        routed = route_note(note)
        print(f"{note.id}\t{note.anchor_type}\t{routed.path}\t{routed.reason}")


def query(notes_path: Path, anchor_type: str, text: str, top_n: int) -> None:
    notes = load_notes(notes_path)
    if anchor_type == "fixed":
        print("route\tstructural-match")
        print("status\tstub: structural graph matching is intentionally deferred")
        return

    print("route\tprecedent-match")
    for match in precedent_matches(text, notes, top_n=top_n):
        print(f"{match.score:.3f}\t{match.note.id}\t{match.note.title}")


if __name__ == "__main__":
    main()
