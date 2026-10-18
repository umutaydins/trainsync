"""P6.11: the hard guardrails and the chat triggers (ADR 0030)."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

import pytest

from trainsync.coach.guardrails import (
    Trigger,
    Violation,
    excuse_kind,
    fold,
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
        ("canım tatlı çekti", Trigger.CRAVING),
        ("akşam pizza yiyeceğim", Trigger.CRAVING),
        ("craving junk food", Trigger.CRAVING),
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
