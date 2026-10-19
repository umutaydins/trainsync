"""Neutral tone, Turkish."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from trainsync.modules.coach.packs.keys import Key
from trainsync.modules.coach.packs.pack import MessagePack

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
            "/stats [week|month|3m|6m|year|all]: önceki döneme göre ilerleme\n"
            "/stats 12w run: toplamlar ve en iyi hafta (4w|12w|52w, her spor)\n"
            "/status: senkron durumu\n"
            "/today: bugünkü planlı antrenman\n"
            "/log bench 80x5x3: set kaydet (80x5,5,4 ya da bw x12x3 de olur)\n"
            "/done: antrenmanı bitir\n"
            "/plates 102.5: bir tarafa takılacak plakalar\n"
            "/report: günlük rapor\n"
            "/yumusak: 24 saat yumuşak koç · /sert: normale dön\n"
            "/lang: Türkçe / English\n"
            "/swear: max / roast (savage profanity)",
        ),
        Key.NO_ASSISTANT: ("Şimdilik yalnızca komutları anlıyorum.\n\n{help}",),
        Key.UNKNOWN_COMMAND: ("Bilinmeyen komut: /{command}. Neler yapabildiğim: /help",),
        Key.USAGE_STATS: (
            "Kullanım: /stats [week|month|3m|6m|year|all] ya da /stats [4w|12w|52w] [spor], "
            "ör. /stats month",
        ),
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
        Key.PROGRESS_TITLE: ("{label} ({range})",),
        Key.PERIOD_WEEK: ("Bu hafta",),
        Key.PERIOD_MONTH: ("Bu ay",),
        Key.PERIOD_3M: ("Son 3 ay",),
        Key.PERIOD_6M: ("Son 6 ay",),
        Key.PERIOD_YEAR: ("Bu yıl",),
        Key.PERIOD_ALL: ("Tüm zamanlar",),
        Key.DIGEST_WEEK: ("Haftan ({range})",),
        Key.DIGEST_MONTH: ("Ayın ({range})",),
        Key.PROGRESS_ENDURANCE: ("🏃 {count} {noun} · {distance} · {time} {change}",),
        Key.PROGRESS_STRENGTH: ("🏋️ {sessions} antrenman · {sets} set · {tonnage} {change}",),
        Key.PROGRESS_PRS: ("🏆 Yeni rekor: {count}",),
        Key.PROGRESS_CONSISTENCY: ("📅 {days} aktif gün · seri {weeks} hafta",),
        Key.PROGRESS_NONE: ("Bu dönemde kayıt yok.",),
        Key.PROGRESS_RECOVERY: (
            "Bu dönemde hasta ya da sakattın. Önce iyileş; rakamlar bekleyebilir.",
        ),
        # Neutral reports numbers only: no verdict line.
        Key.PROGRESS_UP: ("",),
        Key.PROGRESS_DOWN: ("",),
        Key.PROGRESS_FLAT: ("",),
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
        Key.TODAY_NO_PROGRAM: (
            "Aktif program yok. Web'de bir tane oluştur ya da /log ile serbest kaydet.",
        ),
        Key.TODAY_TITLE: ("Bugün: {program} · {day_name}",),
        Key.TODAY_EXERCISE: ("• {name}: {plan} · {suggested}",),
        Key.TODAY_IN_PROGRESS: ("Devam ediyor: {count} set kaydedildi.",),
        Key.TODAY_FOOTER: ("/log ile kaydet, /done ile bitir.",),
        Key.USAGE_PLATES: ("Kullanım: /plates 102.5",),
        Key.PLATES: ("{target}: bir tarafa {per_side} (bar {bar})",),
        Key.PLATES_NONE: ("sadece bar",),
        Key.PLATES_INEXACT: ("Olabilecek en yakın: {achieved} ({difference} eksik).",),
        Key.USAGE_LOG: ("Kullanım: /log bench 80x5x3 (80x5,5,4 ya da bw x12x3 de olur)",),
        Key.LOG_UNKNOWN_EXERCISE: ('"{query}" adında bir egzersiz bilmiyorum.',),
        Key.LOG_CHOOSE_EXERCISE: ("Hangi egzersiz? Numarasını yaz:\n{choices}",),
        Key.LOG_SAVED: ("Kaydedildi, {exercise}: {sets}. Antrenman hacmi {volume}.",),
        Key.DONE_NO_WORKOUT: ("Bugün açık antrenman yok.",),
        Key.DONE_SUMMARY: (
            "Antrenman bitti: {count} set · {exercises} egzersiz · {volume} · {duration}",
        ),
        Key.PRS_TITLE: ("Yeni rekorlar:",),
        Key.PR_WEIGHT_FOR_REPS: ("🏆 {exercise}: {load} x {reps}",),
        Key.PR_E1RM: ("🏆 {exercise}: e1RM {value}",),
        Key.PR_VOLUME: ("🏆 {exercise}: seans hacmi {value}",),
        Key.CHECKIN_PROMPT: ("Günlük rapor: bugün antrenman yaptın mı?",),
        Key.CHECKIN_REMINDER: ("Hatırlatma: bugünkü rapor hâlâ açık. Bugün antrenman yaptın mı?",),
        Key.CHECKIN_BTN_DONE: ("✅ Yaptım",),
        Key.CHECKIN_BTN_PARTIAL: ("🟡 Kısmen",),
        Key.CHECKIN_BTN_SKIPPED: ("❌ Atladım",),
        Key.CHECKIN_BTN_REST: ("😴 Dinlenme günü",),
        Key.CHECKIN_BTN_SICK: ("🤕 Hasta/sakatlık",),
        Key.CHECKIN_BTN_AS_PLANNED: ("Plandaki gibi",),
        Key.CHECKIN_BTN_STEP: ("{step}",),
        Key.CHECKIN_BTN_SKIP_EXERCISE: ("Egzersizi geç",),
        Key.CHECKIN_BTN_FINISH: ("Bitir",),
        Key.CHECKIN_BTN_EDIT: ("✏️ Düzenle",),
        Key.CHECKIN_EXERCISE: (
            "{index}/{total} {name}\nPlan: {plan} · {suggested}\n"
            "Bir düğmeye dokun ya da 80x5x3, 80x5,5,4 veya bw x12x3 yaz.",
        ),
        Key.CHECKIN_SETS_SAVED: ("Kaydedildi, {name}: {sets}.",),
        Key.CHECKIN_EXERCISE_SKIPPED: ("{name} geçildi.",),
        Key.CHECKIN_ALREADY_LOGGED: ("{name}: bugün zaten kaydedilmiş ({sets}).",),
        Key.CHECKIN_ASK_FREEFORM: (
            "Ne yaptın? Her mesaja bir egzersiz, /log gibi: bench 80x5x3. Bitince Bitir'e dokun.",
        ),
        Key.CHECKIN_INVALID_SETS: (
            "Bunu okuyamadım. 80x5x3, 80x5,5,4 ya da bw x12x3 yaz veya bir düğmeye dokun.",
        ),
        Key.CHECKIN_ASK_REASON: ("Ne engel oldu? Birkaç kelime yaz ya da Geç'e dokun.",),
        Key.CHECKIN_REASON_SAVED: ("Not aldım, teşekkürler.",),
        Key.CHECKIN_SKIPPED_NO_REASON: ("Not aldım.",),
        Key.CHECKIN_REST_SAVED: ("Dinlenme günü kaydedildi. Toparlanma da antrenmanın parçası.",),
        Key.CHECKIN_SICK_SAVED: ("Not aldım. Kendine iyi bak; antrenman bekleyebilir.",),
        Key.CHECKIN_SUMMARY: ("{day} raporu kaydedildi: {status}",),
        Key.CHECKIN_SUMMARY_WORKOUT: ("Antrenman: {count} set · {volume}",),
        Key.CHECKIN_SUMMARY_STREAK: ("Rapor serisi: {days} gün",),
        Key.CHECKIN_STALE: (
            "Bu düğme önceki bir soruya ait. Raporu yeniden başlatmak için /report gönder.",
        ),
        # Coach (P6.11, ADR 0030).
        Key.COACH_REMINDER_BEFORE: ("30 dakika sonra antrenman: {day}, {time}.",),
        Key.COACH_REMINDER_NOW: ("{day} zamanı ({time}).",),
        Key.COACH_NUDGE: ("{day}, saat {time} için planlıydı. Bugün hâlâ vakit var.",),
        Key.COACH_MISSED: ("Bugün antrenman olmadı, {day} planlıydı. Yarın yeni bir gün.",),
        Key.COACH_WORKOUT_START: ("Antrenman başladı: {day}. İyi çalışmalar.",),
        Key.COACH_REST_OVER: ("Dinlenme bitti: sıradaki set.",),
        Key.COACH_UNDER_TARGET: ("{exercise}: {done}, planlanan {target}.",),
        Key.COACH_DONE_GOOD: ("Planlanan bütün setler tamam. Eline sağlık.",),
        Key.COACH_DONE_BAD: ("{missing} planlı set yapılmadı.",),
        Key.COACH_SOFT_ON: ("24 saat yumuşak mod. Kapatmak için /sert.",),
        Key.COACH_SOFT_OFF: ("Yumuşak mod kapandı.",),
        Key.LANG_CHOOSE: ("Botun dilini seç.",),
        Key.LANG_SET: ("Dil ayarlandı: Türkçe.",),
        Key.LANG_USAGE: ("Kullanım: /lang, /lang en veya /lang tr.",),
        Key.SWEAR_CHOOSE: (
            "Savage modda küfür: max (her mesajda) mı, roast (sadece fırçalarda) mı?",
        ),
        Key.SWEAR_SET_MAX: ("Küfür: max. Savage koç açıkken geçerli.",),
        Key.SWEAR_SET_ROAST: ("Küfür: roast. Sadece fırçalarda küfür var.",),
        Key.SWEAR_USAGE: ("Kullanım: /swear, /swear max veya /swear roast.",),
        Key.HELP_POINTER: ("Neler yapabildiğim: /help",),
        Key.COACH_FACT_SESSION: ("{day} · {time}",),
        Key.COACH_FACT_UNDER: ("{exercise}: {done}, hedef {target}.",),
        Key.COACH_FACT_MISSING: ("{missing} planlı set eksik.",),
        Key.COACH_ACTION_PLANNED: ("Bugün: {day}, {time}.",),
        Key.COACH_ACTION_FALLBACK: ("Bugün: 20 dakika yürüyüş, şimdi.",),
        Key.COACH_FREE_WORKOUT: ("serbest antrenman",),
    },
)
