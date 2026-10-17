"""Turn locust's `*_stats.csv` into a markdown table: RPS, p50/p95/p99 and error rate.

Usage: `uv run python scripts/loadtest_summary.py loadtest/results/run_stats.csv`
"""

import csv
import sys
from pathlib import Path


def summarize(path: Path) -> str:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    lines = [
        "| Endpoint | Requests | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Errors |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        name = "**All**" if row["Name"] == "Aggregated" else row["Name"]
        requests = int(row["Request Count"])
        failures = int(row["Failure Count"])
        error_pct = 100 * failures / requests if requests else 0.0
        lines.append(
            f"| {name} | {requests:,} | {float(row['Requests/s']):.1f} | {row['50%']} "
            f"| {row['95%']} | {row['99%']} | {error_pct:.2f}% |"
        )
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    print(summarize(Path(sys.argv[1])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
