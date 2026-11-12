"""Question-bank pipeline.

  python -m banana_english.contentbank fetch                   # download the source corpora
  python -m banana_english.contentbank build grammar vocabulary reading listening
  python -m banana_english.contentbank audio                   # listening recordings (Piper)
  python -m banana_english.contentbank import                  # load content/bank into the DB
  python -m banana_english.contentbank audit [--db]            # statistics and quality checks

Needs the `content` dependency group (uv sync --group content) for fetch/build/audio. Every
step resumes where it stopped: parsed text is cached in var/content_cache, audio files that
exist are kept, the import only writes what changed.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m banana_english.contentbank")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fetch")
    build = sub.add_parser("build")
    build.add_argument(
        "skills", nargs="+", choices=["grammar", "vocabulary", "reading", "listening"]
    )
    sub.add_parser("audio")
    sub.add_parser("import")
    audit = sub.add_parser("audit")
    audit.add_argument("--db", action="store_true", help="also check the database tables")
    audit.add_argument("--json", help="write the report as JSON to this file")
    args = parser.parse_args(argv)

    if args.command == "fetch":
        from banana_english.contentbank.sources import fetch

        fetch()
    elif args.command == "build":
        for skill in args.skills:
            if skill == "grammar":
                from banana_english.contentbank.grammar_build import build_grammar

                build_grammar()
            elif skill == "vocabulary":
                from banana_english.contentbank.vocab_build import build_vocabulary

                build_vocabulary()
            elif skill == "reading":
                from banana_english.contentbank.reading_build import build_reading

                build_reading()
            elif skill == "listening":
                from banana_english.contentbank.listening_build import build_listening

                build_listening()
    elif args.command == "audio":
        from banana_english.contentbank.audio import synthesize_all

        synthesize_all()
    elif args.command == "import":
        from sqlalchemy.orm import sessionmaker

        from banana_english.config.settings import Settings
        from banana_english.contentbank.importer import import_bank
        from banana_english.infrastructure.database.repositories import create_db_engine

        engine = create_db_engine(Settings().database_url)
        import_bank(sessionmaker(engine, expire_on_commit=False))
    elif args.command == "audit":
        from banana_english.contentbank.audit import run_audit

        return run_audit(check_db=args.db, json_path=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
