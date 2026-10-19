"""Local wrapper for `python -m trainsync.entrypoints.cli invite …` (P8.1).

    uv run python scripts/invite.py --help

In production run it inside the API container:
`scripts/mac-prod.sh compose exec api python -m trainsync.entrypoints.cli invite …`.
"""

import sys

from trainsync.entrypoints.cli.__main__ import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "invite", *sys.argv[1:]]
    main()
