"""P6.11, P6.13: the hard guardrails and the chat triggers (ADR 0030, 0032)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import pytest

from trainsync.modules.coach.guardrails import (
    FoodKind,
    Trigger,
    Violation,
    excuse_kind,
    fold,
    food_kind,
    mentions_distress,
    mentions_pain,
    violations,
)


def test_fold_is_turkish_aware() -> None:
    assert fold("GÖĞSÜM AĞRIYOR") == fold("göğsüm ağrıyor") == "gogsum agriyor"
    assert fold("İstemiyorum") == "istemiyorum"


@pytest.mark.parametrize(
    "text",
    [
        "Göğsüm ağrıyor",
        "dizim ağrıyor ama gideyim mi",
        "başım dönüyor",
        "Bayılacak gibiyim",
        "sakatlandım galiba",
        "bileğim burkuldu",
        "hastayım, ateşim var",
        "midem bulanıyor",
        "kalbim çok hızlı atıyor",
        "my knee hurts",
        "chest pain since this morning",
        "I feel dizzy",
        "I'm sick",
        "pulled something, I think it's an injury",
    ],
)
def test_pain_injury_illness_is_recognised(text: str) -> None:
    assert mentions_pain(text)


@pytest.mark.parametrize(
    "text",
    [
        "chest day bugün",
        "heart rate 150 civarı",
        "canım istemiyor",
        "broke my PR!",
        "80x5x3",
        "antrenman açıldı",  # "acildi" is not "acil" (emergency)
    ],
)
def test_training_talk_is_not_pain(text: str) -> None:
    assert not mentions_pain(text)


# Regression lists (P6.12): each phrase as typed and without Turkish accents (a phone keyboard
# without them). A missed pain message gets roasted, so when narrowing a pattern would break a
# MUST_TRIGGER phrase, accept the false positive instead.
ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
MUST_TRIGGER = [
    "acil",
    "göğsüm ağrıyor",
    "göğüs ağrısı",
    "başım dönüyor",
    "bayılacak gibiyim",
    "dizim sakatlandı",
    "belim tuttu",
    "kramp girdi",
    "nefes alamıyorum",
    "hastayım",
    "ateşim var",
    "chest pain",
    "I'm dizzy",
    "pulled a muscle",
    "I'm injured",
    "I'm sick",
]
MUST_NOT_TRIGGER = ["antrenman açıldı", "acıktım", "acı biber"]


def with_and_without_accents(phrases: list[str]) -> list[str]:
    return sorted({variant for p in phrases for variant in (p, p.translate(ASCII))})


@pytest.mark.parametrize("text", with_and_without_accents(MUST_TRIGGER))
def test_regression_pain_always_triggers(text: str) -> None:
    assert mentions_pain(text), text
    assert mentions_pain(f"Bugün gelemem, {text}."), text  # inside a longer message too


@pytest.mark.parametrize("text", with_and_without_accents(MUST_NOT_TRIGGER))
def test_regression_everyday_words_never_trigger(text: str) -> None:
    assert not mentions_pain(text), text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("canım istemiyor bugün", Trigger.EXCUSE),
        ("canım istemedi", Trigger.EXCUSE),
        ("yarın yaparım", Trigger.EXCUSE),
        ("bu hafta gitmeyeceğim", Trigger.EXCUSE),
        ("bugün pas", Trigger.EXCUSE),
        ("üşendim valla", Trigger.EXCUSE),
        ("I'll do it tomorrow", Trigger.EXCUSE),
        ("canım tatlı çekti", Trigger.FOOD),
        ("akşam pizza yiyeceğim", Trigger.FOOD),
        ("craving junk food", Trigger.FOOD),
        ("bugün ne var?", None),
        ("yarın planda ne var?", None),
    ],
)
def test_triggers(text: str, expected: Trigger | None) -> None:
    assert excuse_kind(text) == expected


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("şişko gibi oturma", Violation.BODY),
        ("göbeğine bak", Violation.BODY),
        ("you look fat", Violation.BODY),
        ("lose weight already", Violation.BODY),
        ("ibne gibi kaldırıyorsun", Violation.SLUR),
        ("özürlü müsün", Violation.SLUR),
        ("orospu", Violation.SLUR),
        ("burn it off at the gym", Violation.CALORIE_PUNISHMENT),
        ("bugün aç kal", Violation.CALORIE_PUNISHMENT),
        ("öğün atla", Violation.CALORIE_PUNISHMENT),
        # ADR 0032: never below the target, never compensate
        ("eat less tomorrow", Violation.CALORIE_PUNISHMENT),
        ("stay below your target to make up for it", Violation.CALORIE_PUNISHMENT),
        ("make up for it with extra cardio", Violation.CALORIE_PUNISHMENT),
        ("extra cardio to fix the cake", Violation.CALORIE_PUNISHMENT),
        ("yarın daha az ye", Violation.CALORIE_PUNISHMENT),
        ("kardiyoyla yak bunu", Violation.CALORIE_PUNISHMENT),
        ("yarın telafi et", Violation.CALORIE_PUNISHMENT),
        ("kalori hedefinin altında kal", Violation.CALORIE_PUNISHMENT),
    ],
)
def test_violations(text: str, kind: Violation) -> None:
    assert kind in violations(text)


def test_profanity_is_never_a_violation() -> None:
    swearing = "Amına koyayım, siktir git kalk, hassiktir, amk, ulan, lan, sikeyim böyle işi."
    assert violations(swearing) == []
    assert violations(swearing, line=False) == []


def test_generated_replies_may_talk_about_the_bar() -> None:
    reply = "Top set weight was 80 kg; your body of work this week: 4 sessions."
    assert violations(reply, line=False) == []
    assert Violation.BODY in violations("lose weight", line=True)


@pytest.mark.parametrize(
    "text",
    [
        "yediğime pişmanım",
        "kendimi suçlu hissediyorum",
        "baklava yedim sonra kustum",
        "kendimi kusturdum",
        "bugün hiçbir şey yemedim",
        "sabahtan beri yemedim",
        "kendimden nefret ediyorum",
        "değersizim",
        "dün gece tıkındım",
        "kendimi durduramadım",
        "I feel so guilty",
        "I threw up",
        "I made myself sick",
        "haven't eaten all day",
        "I didn't eat anything today",
        "I hate myself",
        "I'm worthless",
        "I want to die",
        "binged last night",
        "couldn't stop eating",
    ],
)
def test_distress_is_recognised(text: str) -> None:
    assert mentions_distress(text), text
    assert mentions_distress(text.upper()), text


@pytest.mark.parametrize(
    "text",
    ["bugün ne yedim?", "akşam yemeği yedim", "antrenman bitti", "I ate lunch", "bench day"],
)
def test_everyday_talk_is_not_distress(text: str) -> None:
    assert not mentions_distress(text), text


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("Bu akşam baklava yiyeceğim", FoodKind.SWEET),
        ("canım çikolata çekti", FoodKind.SWEET),
        ("bir kutu kola içtim", FoodKind.SWEET),
        ("enerji içeceği aldım", FoodKind.SWEET),
        ("doğum günü pastası var", FoodKind.SWEET),
        ("having dessert", FoodKind.SWEET),
        ("energy drink before the gym", FoodKind.SWEET),
        ("akşam hamburger", FoodKind.FAST_FOOD),
        ("döner yiyeceğim", FoodKind.FAST_FOOD),
        ("pizza tonight", FoodKind.FAST_FOOD),
        ("patates kızartması", FoodKind.FRIED),
        ("cips açtım", FoodKind.FRIED),
        ("fried chicken", FoodKind.FRIED),
        ("akşam rakı var", FoodKind.ALCOHOL),
        ("iki bira içtim", FoodKind.ALCOHOL),
        ("wine with dinner", FoodKind.ALCOHOL),
        ("sigara yaktım", FoodKind.SMOKING),
        ("I smoked two", FoodKind.SMOKING),
        ("vape bitti", FoodKind.SMOKING),
        ("sabaha kadar dizi izledim", FoodKind.LATE),
        ("gece 3te yattım", FoodKind.LATE),
        ("stayed up late gaming", FoodKind.LATE),
    ],
)
def test_unhealthy_choices_are_recognised(text: str, kind: FoodKind) -> None:
    assert food_kind(text) is kind
    assert excuse_kind(text) is Trigger.FOOD


@pytest.mark.parametrize(
    "text",
    [
        "birazdan geliyorum",
        "rakip güçlü",
        "kolay gelsin",
        "biraz yorgunum",
        "makarna ve tavuk",
        "pasta with chicken",
        "kale salad",
        "sweet session today",
    ],
)
def test_ordinary_words_are_not_food_triggers(text: str) -> None:
    assert food_kind(text) is None, text
