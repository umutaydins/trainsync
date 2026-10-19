"""The deterministic bot commands (`/week`, `/last`, `/stats`, `/status`, `/help`): each maps
to fixed read-API calls and a formatting function."""

from datetime import date, timedelta

from trainsync.core.clock import Clock
from trainsync.modules.activities.reads import week_start
from trainsync.modules.chat import formatting, progress
from trainsync.modules.chat.read_api import ReadApi
from trainsync.modules.coach.packs import Key, Messages
from trainsync.modules.coach.voice import CoachVoice

DAY = timedelta(days=1)
WEEK = timedelta(days=7)

COMMANDS = frozenset({"start", "help", "week", "last", "stats", "status"})
PERIODS = {"4w": 4, "12w": 12, "52w": 52}
DEFAULT_PERIOD = "4w"
_SPORT_ALIASES = {
    "run": "Run",
    "trailrun": "TrailRun",
    "ride": "Ride",
    "bike": "Ride",
    "gravelride": "GravelRide",
    "virtualride": "VirtualRide",
    "swim": "Swim",
    "walk": "Walk",
    "hike": "Hike",
}


class UsageError(Exception):
    """Bad command arguments; the dispatcher shows the usage message for `key`."""

    def __init__(self, key: Key) -> None:
        super().__init__(key)
        self.key = key


def parse_command(text: str) -> tuple[str | None, list[str]]:
    """`/stats@my_bot 12w Run` → ("stats", ["12w", "Run"]); plain text → (None, [])."""
    text = text.strip()
    if not text.startswith("/"):
        return None, []
    head, *args = text.split()
    return head[1:].split("@", 1)[0].lower(), args


def parse_stats_args(args: list[str]) -> tuple[str, str | None]:
    """`[4w|12w|52w] [sport]` in either order → (period, sport_type)."""
    period, sport = DEFAULT_PERIOD, None
    for arg in args:
        if arg.lower() in PERIODS:
            period = arg.lower()
        elif sport is None:
            sport = _SPORT_ALIASES.get(arg.lower(), arg[:1].upper() + arg[1:])
        else:
            raise UsageError(Key.USAGE_STATS)
    return period, sport


def week_ranges(today: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """(this ISO week so far, the whole previous ISO week)."""
    monday = week_start(today)
    return (monday, today), (monday - WEEK, monday - DAY)


def period_range(today: date, weeks: int) -> tuple[date, date]:
    """The last `weeks` ISO weeks, the current (partial) one included."""
    return week_start(today) - timedelta(weeks=weeks - 1), today


class Commands:
    def __init__(
        self, api: ReadApi, clock: Clock, msg: Messages, voice: CoachVoice | None = None
    ) -> None:
        self._api = api
        self._clock = clock
        self._msg = msg
        self._voice = voice  # the progress verdict in savage (P8.11)

    async def run(self, command: str, args: list[str]) -> str:
        if command == "week":
            return await self.week()
        if command == "last":
            return await self.last()
        if command == "stats":
            return await self.stats(args)
        if command == "status":
            return await self.status()
        return self._msg.help()  # start, help

    async def week(self) -> str:
        now = self._clock()
        (this_from, this_to), (last_from, last_to) = week_ranges(now.date())
        this_week = await self._api.summary(this_from, this_to)
        last_week = await self._api.summary(last_from, last_to)
        return formatting.format_week(this_week, last_week, now, self._msg)

    async def last(self) -> str:
        page = await self._api.activities(limit=1)
        latest = page.items[0] if page.items else None
        return formatting.format_last(latest, page.last_synced_at, self._clock(), self._msg)

    async def stats(self, args: list[str]) -> str:
        """`/stats [week|month|3m|6m|year|all]`: progress (P8.11); `/stats 12w run`: totals."""
        if not args or (len(args) == 1 and args[0].lower() in progress.BOT_PERIODS):
            return await self.progress(args[0].lower() if args else progress.DEFAULT_BOT_PERIOD)
        period, sport = parse_stats_args(args)
        now = self._clock()
        start, end = period_range(now.date(), PERIODS[period])
        summary = await self._api.summary(start, end, sport)
        weekly = await self._api.weekly(start, end, sport)
        return formatting.format_stats(summary, weekly.weeks, period, now, self._msg)

    async def progress(self, choice: str) -> str:
        period, title = progress.BOT_PERIODS[choice]
        summary = await self._api.progress(period)
        return await progress.progress_message(summary, title, self._msg, self._voice)

    async def status(self) -> str:
        return formatting.format_status(await self._api.sync_status(), self._clock(), self._msg)
