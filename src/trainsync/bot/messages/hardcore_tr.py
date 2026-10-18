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
            "/status: senkron durumu\n"
            "/today: bugünkü planlı antrenman\n"
            "/log bench 80x5x3: set kaydet (80x5,5,4 ya da bw x12x3 de olur)\n"
            "/done: antrenmanı bitir\n"
            "/plates 102.5: bir tarafa takılacak plakalar\n"
            "/report: günlük rapor\n"
            "/yumusak: 24 saat yumuşak koç · /sert: normale dön\n"
            "/lang: Türkçe / English",
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
        Key.TODAY_NO_PROGRAM: ("Aktif program yok. Web'de kur ya da kaldır ve /log ile yaz.",),
        Key.TODAY_TITLE: ("Bugün: {program} · {day_name}. Kaçmak yok.",),
        Key.TODAY_EXERCISE: NEUTRAL.texts[Key.TODAY_EXERCISE],
        Key.TODAY_IN_PROGRESS: ("{count} set tamam. Devam.",),
        Key.TODAY_FOOTER: ("/log ile kaydet, /done ile bitir. Hadi.",),
        Key.USAGE_PLATES: ("Yanlış. Kullanım: /plates 102.5",),
        Key.PLATES: NEUTRAL.texts[Key.PLATES],
        Key.PLATES_NONE: NEUTRAL.texts[Key.PLATES_NONE],
        Key.PLATES_INEXACT: NEUTRAL.texts[Key.PLATES_INEXACT],
        Key.USAGE_LOG: ("Yanlış. Kullanım: /log bench 80x5x3 (80x5,5,4 ya da bw x12x3 de olur)",),
        Key.LOG_UNKNOWN_EXERCISE: ('"{query}" diye bir egzersiz yok lan.',),
        Key.LOG_CHOOSE_EXERCISE: ("Hangisi? Numarayı yaz, çabuk:\n{choices}",),
        Key.LOG_SAVED: (
            "Kaydedildi, {exercise}: {sets}. Hacim {volume}. Sıradaki set.",
            "{exercise}: {sets} cebe. Hacim {volume}.",
            "Tamam. {exercise}: {sets}. Hacim {volume}. Durmak yok.",
        ),
        Key.DONE_NO_WORKOUT: ("Bugün açık antrenman yok. /log ile başla.",),
        Key.DONE_SUMMARY: (
            "Bitti: {count} set · {exercises} egzersiz · {volume} · {duration}. Helal.",
        ),
        Key.PRS_TITLE: ("Yeni rekorlar. Hassiktir, işte bu:",),
        Key.PR_WEIGHT_FOR_REPS: NEUTRAL.texts[Key.PR_WEIGHT_FOR_REPS],
        Key.PR_E1RM: NEUTRAL.texts[Key.PR_E1RM],
        Key.PR_VOLUME: NEUTRAL.texts[Key.PR_VOLUME],
        Key.CHECKIN_PROMPT: ("Koç burada. Bugün antrenman yaptın mı?",),
        Key.CHECKIN_REMINDER: ("Bugünkü raporu hâlâ bekliyorum. Antrenman yaptın mı?",),
        Key.CHECKIN_BTN_DONE: NEUTRAL.texts[Key.CHECKIN_BTN_DONE],
        Key.CHECKIN_BTN_PARTIAL: NEUTRAL.texts[Key.CHECKIN_BTN_PARTIAL],
        Key.CHECKIN_BTN_SKIPPED: NEUTRAL.texts[Key.CHECKIN_BTN_SKIPPED],
        Key.CHECKIN_BTN_REST: NEUTRAL.texts[Key.CHECKIN_BTN_REST],
        Key.CHECKIN_BTN_SICK: NEUTRAL.texts[Key.CHECKIN_BTN_SICK],
        Key.CHECKIN_BTN_AS_PLANNED: NEUTRAL.texts[Key.CHECKIN_BTN_AS_PLANNED],
        Key.CHECKIN_BTN_STEP: NEUTRAL.texts[Key.CHECKIN_BTN_STEP],
        Key.CHECKIN_BTN_SKIP_EXERCISE: NEUTRAL.texts[Key.CHECKIN_BTN_SKIP_EXERCISE],
        Key.CHECKIN_BTN_FINISH: NEUTRAL.texts[Key.CHECKIN_BTN_FINISH],
        Key.CHECKIN_BTN_EDIT: NEUTRAL.texts[Key.CHECKIN_BTN_EDIT],
        Key.CHECKIN_EXERCISE: NEUTRAL.texts[Key.CHECKIN_EXERCISE],
        Key.CHECKIN_SETS_SAVED: ("Kaydedildi, {name}: {sets}. Sıradaki.",),
        Key.CHECKIN_EXERCISE_SKIPPED: ("{name} geçildi. Not aldım.",),
        Key.CHECKIN_ALREADY_LOGGED: NEUTRAL.texts[Key.CHECKIN_ALREADY_LOGGED],
        Key.CHECKIN_ASK_FREEFORM: NEUTRAL.texts[Key.CHECKIN_ASK_FREEFORM],
        Key.CHECKIN_INVALID_SETS: (
            "Okuyamadım. 80x5x3, 80x5,5,4 ya da bw x12x3 yaz veya bir düğmeye dokun.",
        ),
        Key.CHECKIN_ASK_REASON: ("Atladın. Neden? Birkaç kelime yaz ya da Geç'e dokun.",),
        Key.CHECKIN_REASON_SAVED: ("Not aldım. Yarın önemli.",),
        Key.CHECKIN_SKIPPED_NO_REASON: (
            "Sebep yok mu? O zaman bahane de yok. Yarın antrenman var.",
            "Sebepsiz atladın ulan. Yarın oradasın.",
            "Söyleyecek bir şey yok mu? Peki. Yarını boş geçme.",
        ),
        # Calm in every tone (ADR 0020): no pushing on rest or illness.
        Key.CHECKIN_REST_SAVED: ("Dinlenme günü kaydedildi. Toparlanma da antrenmanın parçası.",),
        Key.CHECKIN_SICK_SAVED: ("Not aldım. Önce iyileş; antrenman bekleyebilir.",),
        Key.CHECKIN_SUMMARY: NEUTRAL.texts[Key.CHECKIN_SUMMARY],
        Key.CHECKIN_SUMMARY_WORKOUT: NEUTRAL.texts[Key.CHECKIN_SUMMARY_WORKOUT],
        Key.CHECKIN_SUMMARY_STREAK: ("Rapor serisi: {days} gün. Bozma.",),
        Key.CHECKIN_STALE: NEUTRAL.texts[Key.CHECKIN_STALE],
        # Coach (P6.11, ADR 0030).
        Key.COACH_REMINDER_BEFORE: ("30 dakika sonra {day} ({time}). Çantayı hazırla.",),
        Key.COACH_REMINDER_NOW: ("{day}. Saat {time}. Başla.",),
        Key.COACH_NUDGE: ("{day}, saat {time}. Hâlâ yok. Ulan, kalk.",),
        Key.COACH_MISSED: ("{day} bugündü. Olmadı. Yarın oradasın.",),
        Key.COACH_WORKOUT_START: ("{day} başladı. Telefon yok, set var.",),
        Key.COACH_REST_OVER: ("Dinlenme bitti. Sıradaki set.",),
        Key.COACH_UNDER_TARGET: ("{exercise}: {done}, hedef {target}. Sıradakinde düzelt.",),
        Key.COACH_DONE_GOOD: ("Bütün setler tamam. İş bu. Bir dahakine yine.",),
        Key.COACH_DONE_BAD: ("{missing} planlı set yapılmadı. Lan, bir dahakine bitir.",),
        Key.COACH_SOFT_ON: ("Tamam. 24 saat yumuşak mod. Hazır olunca /sert.",),
        Key.COACH_SOFT_OFF: ("Yumuşak mod kapandı. İşe dön.",),
        Key.LANG_CHOOSE: ("Dilini seç. Sonra işine dön.",),
        Key.LANG_SET: ("Tamam, Türkçe. Kurallar aynı, bahane yok.",),
        Key.LANG_USAGE: ("/lang, /lang en ya da /lang tr. Bu kadar basit lan.",),
        Key.COACH_FACT_SESSION: NEUTRAL.texts[Key.COACH_FACT_SESSION],
        Key.COACH_FACT_UNDER: NEUTRAL.texts[Key.COACH_FACT_UNDER],
        Key.COACH_FACT_MISSING: NEUTRAL.texts[Key.COACH_FACT_MISSING],
        Key.COACH_ACTION_PLANNED: NEUTRAL.texts[Key.COACH_ACTION_PLANNED],
        Key.COACH_ACTION_FALLBACK: NEUTRAL.texts[Key.COACH_ACTION_FALLBACK],
        Key.COACH_FREE_WORKOUT: NEUTRAL.texts[Key.COACH_FREE_WORKOUT],
    },
)
