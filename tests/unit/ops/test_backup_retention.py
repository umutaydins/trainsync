"""Backup retention (P7.4, ADR 0024): 7 daily / 4 weekly / 6 monthly, newest always kept;
pre-deploy backups outside the buckets, the newest 3 always kept."""

from datetime import UTC, date, datetime, timedelta

from trainsync.ops.retention import Policy, backup_name, counts_name, parse_name, plan

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)  # a Sunday (ISO week 42)


def name(day: str, at: str = "00:30:00") -> str:
    return backup_name(datetime.fromisoformat(f"{day}T{at}+00:00"))


def nightly(first: str, last: str) -> list[str]:
    start, end = date.fromisoformat(first), date.fromisoformat(last)
    return [name((start + timedelta(days=i)).isoformat()) for i in range((end - start).days + 1)]


def days(names: tuple[str, ...]) -> set[str]:
    out = set()
    for n in names:
        backup = parse_name(n)
        assert backup is not None
        out.add(backup.taken_at.date().isoformat())
    return out


def test_names_round_trip_and_sidecar() -> None:
    taken = datetime(2026, 10, 18, 0, 30, 5, tzinfo=UTC)
    assert backup_name(taken) == "trainsync-20261018-003005.dump.age"
    assert backup_name(taken, "predeploy") == "trainsync-20261018-003005-predeploy.dump.age"
    parsed = parse_name("trainsync-20261018-003005-predeploy.dump.age")
    assert parsed is not None
    assert parsed.taken_at == taken
    assert counts_name(backup_name(taken)) == "trainsync-20261018-003005.counts.json"


def test_unparsable_names_are_ignored_never_deleted() -> None:
    odd = [
        "notes.txt",
        "trainsync-20261318-003000.dump.age",  # month 13
        ".trainsync-20261018-003000.dump.age.partial",
        "trainsync-20261018-003000.counts.json",
        "trainsync-20261018-003000-Upper.dump.age",
    ]
    result = plan([*odd, name("2026-10-18")], NOW)
    assert set(result.ignored) == set(odd)
    assert result.delete == ()
    assert result.keep == (name("2026-10-18"),)


def test_empty_directory() -> None:
    result = plan([], NOW)
    assert (result.keep, result.delete, result.ignored) == ((), (), ())


def test_a_year_of_nightly_backups() -> None:
    result = plan(nightly("2025-10-01", "2026-10-18"), NOW)
    daily = {f"2026-10-{d}" for d in range(12, 19)}
    weekly = {"2026-10-11", "2026-10-04", "2026-09-27"}  # + 2026-10-18 (already daily)
    monthly = {"2026-09-30", "2026-08-31", "2026-07-31", "2026-06-30", "2026-05-31"}
    assert days(result.keep) == daily | weekly | monthly
    assert len(result.keep) + len(result.delete) == 383


def test_newest_backup_of_a_day_wins() -> None:
    early, late = name("2026-10-18", "00:30:00"), name("2026-10-18", "09:00:00")
    result = plan([early, late], NOW)
    assert result.keep == (late,)
    assert result.delete == (early,)


def test_month_boundary() -> None:
    september = name("2026-09-30", "23:59:59")
    october = name("2026-10-01", "00:00:01")
    now = datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
    only_months = Policy(daily=0, weekly=0, monthly=2)
    assert plan([september, october], now, only_months).delete == ()
    assert plan([september, october], now, Policy(daily=0, weekly=0, monthly=1)).delete == (
        september,
    )


def test_iso_weeks_cross_the_year_boundary() -> None:
    sunday_w52 = name("2025-12-28")
    monday_w1, thursday_w1 = name("2025-12-29"), name("2026-01-01")
    now = datetime(2026, 1, 2, tzinfo=UTC)
    result = plan([sunday_w52, monday_w1, thursday_w1], now, Policy(daily=0, weekly=2, monthly=0))
    assert result.keep == tuple(sorted([sunday_w52, thursday_w1]))
    assert result.delete == (monday_w1,)


def test_a_gap_does_not_wipe_out_older_backups() -> None:
    """Buckets count days *with* a backup: after two months off, August is still there."""
    result = plan([*nightly("2026-08-01", "2026-08-10"), name("2026-10-18")], NOW)
    assert days(result.keep) == {
        "2026-10-18",
        *(f"2026-08-{d:02d}" for d in range(5, 11)),  # daily: 6 more days with a backup
        "2026-08-02",  # weekly: ISO week 31 (Aug 1-2)
    }
    assert days(result.delete) == {"2026-08-01", "2026-08-03", "2026-08-04"}


def test_backups_from_the_future_are_kept_and_take_no_bucket() -> None:
    future = name("2026-10-20")
    result = plan([future, *nightly("2026-10-01", "2026-10-18")], NOW, Policy(1, 0, 0))
    assert future in result.keep
    assert name("2026-10-18") in result.keep
    assert len(result.keep) == 2


def test_the_newest_backup_is_never_deleted() -> None:
    backups = [name("2024-01-01"), name("2025-01-01"), name("2026-01-01")]
    result = plan(backups, NOW, Policy(daily=0, weekly=0, monthly=0))
    assert result.keep == (name("2026-01-01"),)
    assert len(result.delete) == 2


def predeploy(day: str, sha: str = "1a2b3c4", at: str = "10:00:00") -> str:
    return backup_name(datetime.fromisoformat(f"{day}T{at}+00:00"), f"predeploy{sha}")


def test_a_predeploy_backup_does_not_take_a_nightly_bucket() -> None:
    nightly_one, before_deploy = name("2026-10-18"), predeploy("2026-10-18")
    result = plan([nightly_one, before_deploy], NOW)
    assert set(result.keep) == {nightly_one, before_deploy}
    assert result.delete == ()


def test_the_newest_three_predeploy_backups_are_always_kept() -> None:
    deploys = [predeploy(f"2026-{m:02d}-01", sha=f"{m:07d}") for m in range(1, 7)]
    result = plan([*deploys, *nightly("2026-10-01", "2026-10-18")], NOW)
    assert [n for n in result.keep if "predeploy" in n] == deploys[-3:]
    assert set(deploys[:3]) <= set(result.delete)


def test_old_predeploy_backups_survive_any_policy() -> None:
    """Even with every bucket at zero and many newer nightly backups."""
    deploys = [predeploy("2025-01-01", "aaaaaaa"), predeploy("2025-02-01", "bbbbbbb")]
    result = plan([*deploys, *nightly("2026-10-01", "2026-10-18")], NOW, Policy(0, 0, 0))
    assert set(deploys) <= set(result.keep)
    assert name("2026-10-18") in result.keep  # the newest nightly one, as always


def test_other_labels_still_take_part_in_retention() -> None:
    manual = backup_name(datetime(2026, 10, 18, 10, 0, tzinfo=UTC), "manual")
    result = plan([name("2026-10-18"), manual], NOW)
    assert result.keep == (manual,)
