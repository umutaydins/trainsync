"""Hardcore tone, Turkish: "Koç", an original tough-love running coach (ADR 0016).

Short, blunt sentences; mild profanity only (lan, ulan, hassiktir). Pushes on effort and
consistency, never on the athlete's body, appearance or identity (tests/unit/test_bot_messages.py
checks a blocklist).
"""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from trainsync.bot.messages.keys import Key
from trainsync.bot.messages.neutral_tr import PACK as NEUTRAL
from trainsync.bot.messages.pack import MessagePack

PACK = MessagePack(
    tone="hardcore",
    lang="tr",
    months=NEUTRAL.months,
    weekdays=NEUTRAL.weekdays,
    texts={
        Key.HELP: (
            "Koç burada. Komutlar var, bahane yok.\n"
            "/week: bu hafta ve geçen hafta\n"
            "/last: son aktivite\n"
            "/stats [4w|12w|52w] [spor]: toplamlar ve en iyi hafta, ör. /stats 12w run\n"
            "/status: senkron durumu",
        ),
        Key.NO_ASSISTANT: ("Sohbet yok, sadece komut.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("/{command} diye bir şey yok lan.\n\n{help}",),
        Key.USAGE_STATS: ("Yanlış. Kullanım: /stats [4w|12w|52w] [spor], ör. /stats 12w run",),
        Key.API_DOWN: (
            "trainsync API'ye ulaşamıyorum. Bu sefer suç sende değil. Bir dakika sonra dene.",
            "API çöktü ulan. Sen o arada koş. Bir dakika sonra dene.",
            "Hassiktir, API cevap vermiyor. Bir dakika ver.",
        ),
        Key.WEEK_THIS: ("Bu hafta ({range})",),
        Key.WEEK_LAST: ("Geçen hafta ({range})",),
        Key.WEEK_NONE_YET: (
            "Daha hiçbir şey yok. Hafta kendi kendine koşmaz.",
            "Şu ana kadar sıfır. Ayakkabılar kapının önünde.",
            "Boş. Düzelt bunu.",
        ),
        Key.WEEK_NONE: ("Hiçbir şey.",),
        Key.WEEK_DELTA: NEUTRAL.texts[Key.WEEK_DELTA],
        Key.VERDICT_PUSH: (
            "Geçen haftanın %{percent} kadarı. Lan, bu antrenman değil. Çık dışarı.",
            "Geçen haftanın sadece %{percent} kadarı. Pazarlığı bırak, bugün koş.",
            "Geçen haftaya göre %{percent}. Ulan, yarın değil, bugün.",
        ),
        Key.VERDICT_STEADY: (
            "Geçen haftanın %{percent} kadarı. Yaklaştın. İşi bitir.",
            "Geçen haftanın %{percent} kadarı. Fena değil, ama bitmedi.",
            "Geçen haftaya göre %{percent}. Günleri üst üste koymaya devam.",
        ),
        Key.VERDICT_UP: (
            "En az geçen hafta kadar. Aferin. Gelecek hafta biraz daha fazlası.",
            "Geçen haftanın gerisinde kalmadın. Helal. Şimdi bir antrenman ekle.",
            "Geçen haftanın çıtası geçildi. Hassiktir, güzel. Ama rahatlama.",
        ),
        Key.VERDICT_ZERO_STREAK: (
            "İki haftadır sıfır. Sakatlık mı, dinlenme mi? Söyle, ona göre plan yapalım.",
            "Geçen hafta yok, bu hafta yok. Sakatlık mı var, yoksa planlı bir ara mı?",
            "Üst üste iki boş hafta. Sakatlık mı, dinlenme mi? Dürüst ol.",
        ),
        Key.LAST_NONE: (
            "Daha aktivite yok. Yorumlayacak bir şey yok. Git bir tane yap.",
            "Kayıt yok ulan. Bugün başla.",
            "Boş liste. Kısa bir koşu bunu düzeltir.",
        ),
        Key.LAST_HEARTRATE: NEUTRAL.texts[Key.LAST_HEARTRATE],
        Key.ACTIVITY_WHEN: NEUTRAL.texts[Key.ACTIVITY_WHEN],
        Key.STATS_TITLE: NEUTRAL.texts[Key.STATS_TITLE],
        Key.STATS_NONE: ("Bu aralıkta hiçbir şey yok lan.",),
        Key.STATS_BEST_WEEK: ("En iyi hafta: {day} · {distance} · {time}. Geç onu.",),
        Key.STATS_LONGEST: NEUTRAL.texts[Key.STATS_LONGEST],
        Key.TOTALS: NEUTRAL.texts[Key.TOTALS],
        Key.ACTIVITY_ONE: NEUTRAL.texts[Key.ACTIVITY_ONE],
        Key.ACTIVITY_MANY: NEUTRAL.texts[Key.ACTIVITY_MANY],
        Key.FRESH_NEVER: ("⚠️ Henüz senkron yok. Önce Strava'yı bağla.",),
        Key.FRESH_STALE: ("⚠️ Veriler {when} UTC itibarıyla. Bayat.",),
        Key.STATUS_NEVER: NEUTRAL.texts[Key.STATUS_NEVER],
        Key.STATUS_SYNCED: NEUTRAL.texts[Key.STATUS_SYNCED],
        Key.STATUS_WEBHOOKS: NEUTRAL.texts[Key.STATUS_WEBHOOKS],
        Key.STATUS_CIRCUIT: NEUTRAL.texts[Key.STATUS_CIRCUIT],
        Key.STATUS_RATE_LIMIT: NEUTRAL.texts[Key.STATUS_RATE_LIMIT],
        Key.AGO_NOW: NEUTRAL.texts[Key.AGO_NOW],
        Key.AGO_MINUTES: NEUTRAL.texts[Key.AGO_MINUTES],
        Key.AGO_HOURS: NEUTRAL.texts[Key.AGO_HOURS],
        Key.AGO_DAYS: NEUTRAL.texts[Key.AGO_DAYS],
        Key.NEW_ACTIVITY: (
            "Kaydedildi. İyi.",
            "Bir antrenman daha cepte.",
            "Bu sayılır. Dinlen, sonra yine.",
            "Tamam. Haftanın sonuncusu olmasın.",
        ),
        Key.ASSISTANT_RATE_LIMITED: (
            "Bu saatlik soru hakkın bitti. Git antrenman yap. /week, /stats, /last çalışıyor.",
        ),
        Key.ASSISTANT_TIMED_OUT: ("Çok uzun sürdü. Daha basit sor ya da /stats kullan.",),
        Key.ASSISTANT_UNAVAILABLE: ("Şu an soru yok. Komutlar çalışıyor: /week, /stats, /last.",),
        Key.ASSISTANT_TOO_MANY_CALLS: ("Bunun için çok fazla sorgu lazım. Daralt.",),
        Key.ASSISTANT_REFUSED: ("O benim işim değil. Antrenmanını sor.",),
    },
)
