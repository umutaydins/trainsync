"""Tone-free wording: nutrition, body weight, sleep and energy (P6.8, P6.9).

These texts are the same in every `BOT_TONE`: the scale is never commented on, and food only by the
savage coach's roast of a choice (ADR 0032), which sits next to these lines, not in them. They are
deliberately kept out of the tone packs (tests/unit/modules/coach/packs/test_bot_messages.py checks
that no pack has them and that every language defines every key). One template per key, no variants.
Units are part of the fields (`78.4 kg`), computed in code.
"""

# Turkish words below: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from collections.abc import Mapping
from enum import StrEnum

from trainsync.core.settings import BotLang


class NeutralKey(StrEnum):
    HELP_NUTRITION = "help.nutrition"
    CHOICE_INVALID = "choice.invalid"
    BUTTON_SKIP = "button.skip"

    EAT_USAGE = "eat.usage"
    EAT_NOT_FOUND = "eat.not_found"
    EAT_CHOOSE = "eat.choose"
    EAT_SAVED = "eat.saved"
    MEAL_BREAKFAST = "meal.breakfast"
    MEAL_LUNCH = "meal.lunch"
    MEAL_DINNER = "meal.dinner"
    MEAL_SNACK = "meal.snack"

    KCAL_TITLE = "kcal.title"
    KCAL_NONE = "kcal.none"
    KCAL_INTAKE = "kcal.intake"
    KCAL_INTAKE_TARGET = "kcal.intake_target"
    KCAL_MACROS = "kcal.macros"
    KCAL_MACROS_INCOMPLETE = "kcal.macros_incomplete"
    # The food line of a progress summary (P8.11): a period's daily average.
    KCAL_AVERAGE = "kcal.average"
    KCAL_AVERAGE_TARGET = "kcal.average_target"

    SCALE_USAGE = "scale.usage"
    SCALE_SAVED = "scale.saved"

    CHECKIN_ASK_SCALE = "checkin.ask_scale"
    CHECKIN_ASK_SLEEP = "checkin.ask_sleep"
    CHECKIN_ASK_ENERGY = "checkin.ask_energy"
    CHECKIN_INVALID_NUMBER = "checkin.invalid_number"
    CHECKIN_SUMMARY_SCALE = "checkin.summary.scale"
    CHECKIN_SUMMARY_SLEEP = "checkin.summary.sleep"
    CHECKIN_SUMMARY_ENERGY = "checkin.summary.energy"

    # Coach guardrails (P6.11, ADR 0030): the same in every tone and intensity.
    SAFETY_PAIN = "safety.pain"
    # ADR 0032: the calm reply to distress; the one concrete move after a food roast, and the
    # day's target, unchanged.
    SAFETY_DISTRESS = "safety.distress"
    # Linking a chat to an account (P8.4, ADR 0036): tone-free, an unlinked chat has no tone.
    LINK_HINT = "link.hint"
    LINK_DONE = "link.done"
    LINK_INVALID = "link.invalid"
    LINK_USAGE = "link.usage"
    LINK_ALREADY = "link.already"
    UNLINKED = "link.unlinked"
    FOOD_MOVE_SWEET = "food.move.sweet"
    FOOD_MOVE_FAST_FOOD = "food.move.fast_food"
    FOOD_MOVE_FRIED = "food.move.fried"
    FOOD_MOVE_ALCOHOL = "food.move.alcohol"
    FOOD_MOVE_SMOKING = "food.move.smoking"
    FOOD_MOVE_LATE = "food.move.late"
    FOOD_MOVE_LOGGED = "food.move.logged"
    FOOD_TARGET = "food.target"
    FOOD_NO_TARGET = "food.no_target"
    FOOD_SUGAR_DAY = "food.sugar_day"


def _fields(*names: str) -> frozenset[str]:
    return frozenset(names)


NEUTRAL_FIELDS: Mapping[NeutralKey, frozenset[str]] = {
    NeutralKey.HELP_NUTRITION: _fields("scale_command"),
    NeutralKey.CHOICE_INVALID: _fields("count"),
    NeutralKey.BUTTON_SKIP: _fields(),
    NeutralKey.EAT_USAGE: _fields(),
    NeutralKey.EAT_NOT_FOUND: _fields("query"),
    NeutralKey.EAT_CHOOSE: _fields("choices"),
    NeutralKey.EAT_SAVED: _fields("grams", "food", "meal", "kcal"),
    NeutralKey.MEAL_BREAKFAST: _fields(),
    NeutralKey.MEAL_LUNCH: _fields(),
    NeutralKey.MEAL_DINNER: _fields(),
    NeutralKey.MEAL_SNACK: _fields(),
    NeutralKey.KCAL_TITLE: _fields("day"),
    NeutralKey.KCAL_NONE: _fields(),
    NeutralKey.KCAL_INTAKE: _fields("intake", "entries"),
    NeutralKey.KCAL_INTAKE_TARGET: _fields("intake", "target", "remaining", "entries"),
    NeutralKey.KCAL_MACROS: _fields("protein", "carbs", "fat_g"),
    NeutralKey.KCAL_MACROS_INCOMPLETE: _fields(),
    NeutralKey.KCAL_AVERAGE: _fields("kcal"),
    NeutralKey.KCAL_AVERAGE_TARGET: _fields("kcal", "target"),
    NeutralKey.SCALE_USAGE: _fields("command"),
    NeutralKey.SCALE_SAVED: _fields("day", "value"),
    NeutralKey.CHECKIN_ASK_SCALE: _fields(),
    NeutralKey.CHECKIN_ASK_SLEEP: _fields(),
    NeutralKey.CHECKIN_ASK_ENERGY: _fields(),
    NeutralKey.CHECKIN_INVALID_NUMBER: _fields("example"),
    NeutralKey.CHECKIN_SUMMARY_SCALE: _fields("value"),
    NeutralKey.CHECKIN_SUMMARY_SLEEP: _fields("hours"),
    NeutralKey.CHECKIN_SUMMARY_ENERGY: _fields("energy"),
    NeutralKey.SAFETY_PAIN: _fields(),
    NeutralKey.SAFETY_DISTRESS: _fields("emergency"),
    NeutralKey.LINK_HINT: _fields("url"),
    NeutralKey.LINK_DONE: _fields("name"),
    NeutralKey.LINK_INVALID: _fields(),
    NeutralKey.LINK_USAGE: _fields(),
    NeutralKey.LINK_ALREADY: _fields(),
    NeutralKey.UNLINKED: _fields(),
    NeutralKey.FOOD_MOVE_SWEET: _fields(),
    NeutralKey.FOOD_MOVE_FAST_FOOD: _fields(),
    NeutralKey.FOOD_MOVE_FRIED: _fields(),
    NeutralKey.FOOD_MOVE_ALCOHOL: _fields(),
    NeutralKey.FOOD_MOVE_SMOKING: _fields(),
    NeutralKey.FOOD_MOVE_LATE: _fields(),
    NeutralKey.FOOD_MOVE_LOGGED: _fields(),
    NeutralKey.FOOD_TARGET: _fields("target", "remaining"),
    NeutralKey.FOOD_NO_TARGET: _fields(),
    NeutralKey.FOOD_SUGAR_DAY: _fields("sugar", "limit"),
}

_EN: Mapping[NeutralKey, str] = {
    NeutralKey.HELP_NUTRITION: (
        "/eat <food> <grams>: log food, e.g. /eat oats 60\n"
        "/kcal: today's intake and macros\n"
        "{scale_command} 78.4: today's scale reading"
    ),
    NeutralKey.CHOICE_INVALID: "Reply with a number from 1 to {count}.",
    NeutralKey.BUTTON_SKIP: "Skip",
    NeutralKey.EAT_USAGE: "Usage: /eat <food> <grams>, e.g. /eat oats 60",
    NeutralKey.EAT_NOT_FOUND: 'No food matches "{query}". Add it on the web, then try again.',
    NeutralKey.EAT_CHOOSE: "Which one? Reply with a number:\n{choices}",
    NeutralKey.EAT_SAVED: "Logged {grams} {food} ({meal}): {kcal}.",
    NeutralKey.MEAL_BREAKFAST: "breakfast",
    NeutralKey.MEAL_LUNCH: "lunch",
    NeutralKey.MEAL_DINNER: "dinner",
    NeutralKey.MEAL_SNACK: "snack",
    NeutralKey.KCAL_TITLE: "Food today ({day})",
    NeutralKey.KCAL_NONE: "Nothing logged yet.",
    NeutralKey.KCAL_INTAKE: "{intake} · {entries} entries",
    NeutralKey.KCAL_INTAKE_TARGET: "{intake} of {target} · {remaining} left · {entries} entries",
    NeutralKey.KCAL_MACROS: "Protein {protein} · carbs {carbs} · F {fat_g}",
    NeutralKey.KCAL_MACROS_INCOMPLETE: "Some foods have unknown macros; they are left out.",
    NeutralKey.KCAL_AVERAGE: "🍽️ {kcal} kcal a day",
    NeutralKey.KCAL_AVERAGE_TARGET: "🍽️ {kcal} kcal a day (target {target})",
    NeutralKey.SCALE_USAGE: "Usage: {command} 78.4",
    NeutralKey.SCALE_SAVED: "Saved for {day}: {value}.",
    NeutralKey.CHECKIN_ASK_SCALE: "Scale reading today? Reply like 78.4, or tap Skip.",
    NeutralKey.CHECKIN_ASK_SLEEP: "Hours of sleep last night? Reply like 7.5, or tap Skip.",
    NeutralKey.CHECKIN_ASK_ENERGY: "Energy today, from 1 (low) to 5 (high)?",
    NeutralKey.CHECKIN_INVALID_NUMBER: "Please reply with a number like {example}, or tap Skip.",
    NeutralKey.CHECKIN_SUMMARY_SCALE: "Scale: {value}",
    NeutralKey.CHECKIN_SUMMARY_SLEEP: "Sleep: {hours}",
    NeutralKey.CHECKIN_SUMMARY_ENERGY: "Energy: {energy}/5",
    NeutralKey.SAFETY_PAIN: (
        "That sounds like pain or illness. No training through it: rest, and see a doctor if it "
        "is sharp, in your chest, makes you dizzy or does not go away."
    ),
    NeutralKey.SAFETY_DISTRESS: (
        "No roast here. That sounds heavy, and one day does not undo your work. Have a normal "
        "meal when you can, and log it only if that helps. If this keeps coming back or you do "
        "not feel safe, talk to someone you trust or a professional today (emergency: {emergency})."
    ),
    NeutralKey.LINK_HINT: (
        "This chat is not linked to a trainsync account. Sign in at {url}, open Settings, "
        "Telegram, and send me the /link command shown there."
    ),
    NeutralKey.LINK_DONE: "Linked, {name}. Send /help to see what I can do.",
    NeutralKey.LINK_INVALID: "That code is invalid or expired. Get a new one in the dashboard.",
    NeutralKey.LINK_USAGE: "Send /link and the code from the dashboard, e.g. /link K7Q2M9XD.",
    NeutralKey.LINK_ALREADY: "This chat is already linked. Send /unlink first to link another.",
    NeutralKey.UNLINKED: "Unlinked. This chat gets no more of your data or reminders.",
    NeutralKey.FOOD_MOVE_SWEET: (
        "One move: half the portion, or swap it for fruit with yogurt. Log it with /eat now."
    ),
    NeutralKey.FOOD_MOVE_FAST_FOOD: (
        "One move: one burger or two slices, no fries, water instead of soda. Log it now."
    ),
    NeutralKey.FOOD_MOVE_FRIED: (
        "One move: grilled or baked instead of fried, with a salad next to it. Log it now."
    ),
    NeutralKey.FOOD_MOVE_ALCOHOL: (
        "One move: a proper meal first, two drinks at most, a glass of water between them."
    ),
    NeutralKey.FOOD_MOVE_SMOKING: (
        "One move: not this one. Wait ten minutes, drink a glass of water, walk around the block."
    ),
    NeutralKey.FOOD_MOVE_LATE: (
        "One move: phone away and lights out by 23:30 tonight. Tomorrow's session needs the sleep."
    ),
    NeutralKey.FOOD_MOVE_LOGGED: (
        "Logged, good. One move for next time: half that portion, or swap it for fruit with yogurt."
    ),
    NeutralKey.FOOD_TARGET: "Today's target stays {target}: {remaining} left.",
    NeutralKey.FOOD_NO_TARGET: "Log it with /eat so the day adds up.",
    NeutralKey.FOOD_SUGAR_DAY: "Sugar today: {sugar}, over the {limit} limit.",
}

_TR: Mapping[NeutralKey, str] = {
    NeutralKey.HELP_NUTRITION: (
        "/eat <yiyecek> <gram>: yiyecek kaydet, ör. /eat yulaf 60\n"
        "/kcal: bugünkü alım ve makrolar\n"
        "{scale_command} 78.4: bugünkü tartı"
    ),
    NeutralKey.CHOICE_INVALID: "1 ile {count} arasında bir numara yaz.",
    NeutralKey.BUTTON_SKIP: "Geç",
    NeutralKey.EAT_USAGE: "Kullanım: /eat <yiyecek> <gram>, ör. /eat yulaf 60",
    NeutralKey.EAT_NOT_FOUND: (
        '"{query}" ile eşleşen yiyecek yok. Önce web\'de ekle, sonra tekrar dene.'
    ),
    NeutralKey.EAT_CHOOSE: "Hangisi? Numarasını yaz:\n{choices}",
    NeutralKey.EAT_SAVED: "Kaydedildi: {grams} {food} ({meal}): {kcal}.",
    NeutralKey.MEAL_BREAKFAST: "kahvaltı",
    NeutralKey.MEAL_LUNCH: "öğle",
    NeutralKey.MEAL_DINNER: "akşam",
    NeutralKey.MEAL_SNACK: "ara öğün",
    NeutralKey.KCAL_TITLE: "Bugün yenenler ({day})",
    NeutralKey.KCAL_NONE: "Henüz kayıt yok.",
    NeutralKey.KCAL_INTAKE: "{intake} · {entries} kayıt",
    NeutralKey.KCAL_INTAKE_TARGET: "{intake} / {target} · {remaining} kaldı · {entries} kayıt",
    NeutralKey.KCAL_MACROS: "Protein {protein} · karbonhidrat {carbs} · yağ {fat_g}",
    NeutralKey.KCAL_MACROS_INCOMPLETE: "Bazı yiyeceklerin makroları bilinmiyor; toplama girmedi.",
    NeutralKey.KCAL_AVERAGE: "🍽️ günde {kcal} kcal",
    NeutralKey.KCAL_AVERAGE_TARGET: "🍽️ günde {kcal} kcal (hedef {target})",
    NeutralKey.SCALE_USAGE: "Kullanım: {command} 78.4",
    NeutralKey.SCALE_SAVED: "{day} için kaydedildi: {value}.",
    NeutralKey.CHECKIN_ASK_SCALE: "Bugünkü tartı? 78.4 gibi yaz ya da Geç'e dokun.",
    NeutralKey.CHECKIN_ASK_SLEEP: "Dün gece kaç saat uyudun? 7.5 gibi yaz ya da Geç'e dokun.",
    NeutralKey.CHECKIN_ASK_ENERGY: "Bugün enerjin 1 (düşük) ile 5 (yüksek) arasında kaç?",
    NeutralKey.CHECKIN_INVALID_NUMBER: "{example} gibi bir sayı yaz ya da Geç'e dokun.",
    NeutralKey.CHECKIN_SUMMARY_SCALE: "Tartı: {value}",
    NeutralKey.CHECKIN_SUMMARY_SLEEP: "Uyku: {hours}",
    NeutralKey.CHECKIN_SUMMARY_ENERGY: "Enerji: {energy}/5",
    NeutralKey.SAFETY_PAIN: (
        "Bu ağrı ya da hastalık gibi duruyor. Bununla antrenman yok: dinlen; ağrı keskinse, "
        "göğsündeyse, başın dönüyorsa ya da geçmiyorsa doktora görün."
    ),
    NeutralKey.SAFETY_DISTRESS: (
        "Burada fırça yok. Ağır bir şey gibi duruyor ve tek bir gün emeğini silmez. Fırsat "
        "bulunca normal bir öğün ye, kaydetmek iyi geliyorsa kaydet. Bu tekrar ediyorsa ya da "
        "kendini güvende hissetmiyorsan bugün güvendiğin biriyle ya da bir uzmanla konuş "
        "(acil durumda {emergency})."
    ),
    NeutralKey.LINK_HINT: (
        "Bu sohbet bir trainsync hesabına bağlı değil. {url} adresinde giriş yap, Ayarlar → "
        "Telegram'ı aç ve orada gösterilen /link komutunu bana gönder."
    ),
    NeutralKey.LINK_DONE: "Bağlandı, {name}. Neler yapabildiğimi görmek için /help yaz.",
    NeutralKey.LINK_INVALID: "Bu kod geçersiz ya da süresi dolmuş. Panelden yeni bir kod al.",
    NeutralKey.LINK_USAGE: "/link ve panelden aldığın kodu gönder, örneğin /link K7Q2M9XD.",
    NeutralKey.LINK_ALREADY: "Bu sohbet zaten bağlı. Başka bir hesap için önce /unlink gönder.",
    NeutralKey.UNLINKED: (
        "Bağlantı kaldırıldı. Bu sohbete artık verilerin ve hatırlatmaların gelmez."
    ),
    NeutralKey.FOOD_MOVE_SWEET: (
        "Tek hamle: porsiyonu yarıya indir ya da yoğurtlu meyveyle değiştir. Şimdi /eat ile kaydet."
    ),
    NeutralKey.FOOD_MOVE_FAST_FOOD: (
        "Tek hamle: tek burger ya da iki dilim, patatessiz, kola yerine su. Şimdi kaydet."
    ),
    NeutralKey.FOOD_MOVE_FRIED: (
        "Tek hamle: kızartma yerine ızgara ya da fırın, yanına salata. Şimdi kaydet."
    ),
    NeutralKey.FOOD_MOVE_ALCOHOL: (
        "Tek hamle: önce düzgün bir öğün, en fazla iki kadeh, aralarında bir bardak su."
    ),
    NeutralKey.FOOD_MOVE_SMOKING: (
        "Tek hamle: bu seferki olmasın. On dakika bekle, bir bardak su iç, sokağı bir tur yürü."
    ),
    NeutralKey.FOOD_MOVE_LATE: (
        "Tek hamle: bu gece 23:30'da telefon uzakta, ışıklar kapalı. Yarınki antrenman "
        "uykuyu ister."
    ),
    NeutralKey.FOOD_MOVE_LOGGED: (
        "Kaydettin, iyi. Bir dahaki sefere tek hamle: porsiyonun yarısı ya da yoğurtlu meyve."
    ),
    NeutralKey.FOOD_TARGET: "Bugünkü hedef aynı: {target}, {remaining} kaldı.",
    NeutralKey.FOOD_NO_TARGET: "Gün doğru toplansın diye /eat ile kaydet.",
    NeutralKey.FOOD_SUGAR_DAY: "Bugün şeker: {sugar}, {limit} sınırının üstünde.",
}

NEUTRAL_TEXTS: Mapping[BotLang, Mapping[NeutralKey, str]] = {"en": _EN, "tr": _TR}
