"""Local wrapper for `python -m trainsync.entrypoints.cli owner …` (P8.1).

    uv run python scripts/owner.py --help

In production run it inside the API container:
`scripts/mac-prod.sh compose exec api python -m trainsync.entrypoints.cli owner …`.
"""

import sys

from trainsync.entrypoints.cli.__main__ import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "owner", *sys.argv[1:]]
    main()
