"""Audit the question bank (content/bank): counts, duplicates, invalid records, broken links.

python scripts/audit_content.py            # the bank files
python scripts/audit_content.py --db       # also the database tables
python scripts/audit_content.py --json report.json
"""

import sys

from banana_english.contentbank.__main__ import main

if __name__ == "__main__":
    sys.exit(main(["audit", *sys.argv[1:]]))
