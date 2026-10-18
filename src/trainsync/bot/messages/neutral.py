"""Tone-free wording: nutrition, body weight, sleep and energy (P6.8, P6.9).

These texts are the same in every `BOT_TONE`: food and the scale are never commented on, so they
are deliberately kept out of the tone packs (tests/unit/test_bot_messages.py checks that no pack
has them and that every language defines every key). One template per key, no variants.
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
    FOOD_CRAVING = "food.craving"
    FOOD_CRAVING_NO_TARGET = "food.craving_no_target"


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
    NeutralKey.FOOD_CRAVING: _fields("remaining"),
    NeutralKey.FOOD_CRAVING_NO_TARGET: _fields(),
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
    NeutralKey.FOOD_CRAVING: "Eat it, log it, stay in your daily target: {remaining} left today.",
    NeutralKey.FOOD_CRAVING_NO_TARGET: (
        "Eat it and log it with /eat. Set a daily target on the web to see what is left."
    ),
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
    NeutralKey.FOOD_CRAVING: "Ye, kaydet, günlük hedefinde kal: bugün {remaining} kaldı.",
    NeutralKey.FOOD_CRAVING_NO_TARGET: (
        "Ye ve /eat ile kaydet. Kalanı görmek için web'den günlük hedef koy."
    ),
}

NEUTRAL_TEXTS: Mapping[BotLang, Mapping[NeutralKey, str]] = {"en": _EN, "tr": _TR}
