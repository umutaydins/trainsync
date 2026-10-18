"""Neutral tone, Turkish."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from trainsync.bot.messages.keys import Key
from trainsync.bot.messages.pack import MessagePack

PACK = MessagePack(
    tone="neutral",
    lang="tr",
    months=("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"),
    weekdays=("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"),
    texts={
        Key.HELP: (
            "trainsync botu\n"
            "/week: bu hafta ve geçen hafta\n"
            "/last: son aktivite\n"
            "/stats [4w|12w|52w] [spor]: toplamlar ve en iyi hafta, ör. /stats 12w run\n"
            "/status: senkron durumu",
        ),
        Key.NO_ASSISTANT: ("Şimdilik yalnızca komutları anlıyorum.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("Bilinmeyen komut: /{command}.\n\n{help}",),
        Key.USAGE_STATS: ("Kullanım: /stats [4w|12w|52w] [spor], ör. /stats 12w run",),
        Key.API_DOWN: ("Üzgünüm, şu an trainsync API'ye ulaşamıyorum. Bir dakika sonra dene.",),
        Key.WEEK_THIS: ("Bu hafta ({range})",),
        Key.WEEK_LAST: ("Geçen hafta ({range})",),
        Key.WEEK_NONE_YET: ("Henüz aktivite yok.",),
        Key.WEEK_NONE: ("Aktivite yok.",),
        Key.WEEK_DELTA: ("Mesafe, geçen haftaya göre {delta}",),
        Key.VERDICT_PUSH: ("",),
        Key.VERDICT_STEADY: ("",),
        Key.VERDICT_UP: ("",),
        Key.VERDICT_ZERO_STREAK: ("",),
        Key.LAST_NONE: ("Henüz aktivite yok.",),
        Key.LAST_HEARTRATE: ("♥ ort. {bpm} bpm",),
        Key.ACTIVITY_WHEN: ("{sport} · {when} UTC",),
        Key.STATS_TITLE: ("Son {label}{sport} ({range})",),
        Key.STATS_NONE: ("Aktivite yok.",),
        Key.STATS_BEST_WEEK: ("En iyi hafta: {day} · {distance} · {time}",),
        Key.STATS_LONGEST: ("En uzun: {name} · {distance} ({day})",),
        Key.TOTALS: ("{count} {noun} · {distance} · {time} · {elevation}",),
        Key.ACTIVITY_ONE: ("aktivite",),
        Key.ACTIVITY_MANY: ("aktivite",),
        Key.FRESH_NEVER: ("⚠️ Henüz senkronlanan veri yok.",),
        Key.FRESH_STALE: ("⚠️ Veriler {when} UTC itibarıyla.",),
        Key.STATUS_NEVER: ("hiç senkronlanmadı",),
        Key.STATUS_SYNCED: ("son senkron {ago}",),
        Key.STATUS_WEBHOOKS: ("webhook {pending} bekleyen / {failed} hatalı / {dead} ölü",),
        Key.STATUS_CIRCUIT: ("Strava devresi {state}",),
        Key.STATUS_RATE_LIMIT: ("rate limit %{percent}",),
        Key.AGO_NOW: ("az önce",),
        Key.AGO_MINUTES: ("{n} dk önce",),
        Key.AGO_HOURS: ("{n} sa önce",),
        Key.AGO_DAYS: ("{n} gün önce",),
        Key.NEW_ACTIVITY: ("Yeni aktivite",),
        Key.ASSISTANT_RATE_LIMITED: (
            "Bu saat çok soru sordun. Sonra tekrar dene ya da /week, /stats, /last kullan.",
        ),
        Key.ASSISTANT_TIMED_OUT: (
            "Bunu çözmek çok uzun sürdü. Daha basit bir soru dene ya da /stats.",
        ),
        Key.ASSISTANT_UNAVAILABLE: (
            "Şu an soru cevaplayamıyorum. Komutlar çalışıyor: /week, /stats, /last.",
        ),
        Key.ASSISTANT_TOO_MANY_CALLS: (
            "Bunun için çok fazla sorgu gerekti. Soruyu daraltmayı dene.",
        ),
        Key.ASSISTANT_REFUSED: ("Bu konuda yardımcı olamam. Antrenmanınla ilgili sor.",),
    },
)
