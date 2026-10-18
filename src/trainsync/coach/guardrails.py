"""Hard guardrails of the coach (ADR 0030): the only limits that also hold in savage.

- `mentions_pain`: pain, injury, illness, dizziness, chest pain and the like → no roast, no push.
- `violations`: body/weight/appearance words, identity slurs (ethnicity, religion, sexual
  orientation, disability, gender) and calorie-punishment phrases. Profanity is not on the list
  and is never filtered.
- `excuse_kind`: the excuse / craving phrases that trigger the savage replies.

Matching works on `fold()`ed text: Turkish-aware lower case, and ASCII stand-ins for Turkish
letters, so "Göğsüm ağrıyor", "gogsum agriyor" and "GÖĞSÜM AĞRIYOR" are the same.
"""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001, RUF002

import re
from enum import StrEnum

_ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def fold(text: str) -> str:
    """Lower case the Turkish way (İ → i, I → ı), then map Turkish letters to ASCII."""
    lowered = text.replace("İ", "i").replace("I", "ı").lower()
    return lowered.translate(_ASCII)


def _words(*patterns: str) -> re.Pattern[str]:
    # Each pattern is matched from a word start on the folded text; `\w*` lets Turkish suffixes
    # through ("agriyor", "agrisi", "agrim").
    return re.compile(r"\b(?:" + "|".join(patterns) + r")", re.IGNORECASE)


# ---------------------------------------------------------------- pain, injury, illness

PAIN = _words(
    # Turkish (folded)
    r"agri\w*",
    r"agriy\w*",
    r"sizl\w*",
    r"sakatl\w*",
    r"sakatlan\w*",
    r"incin\w*",
    r"burkul\w*",
    r"zorlan\w* (?:dizim|belim|omzum)",
    r"kas yirti\w*",
    r"yirtil\w*",
    r"kirik\w*",
    r"kiril\w*",
    r"tendon\w*",
    r"bas don\w*",
    r"basim don\w*",
    r"goz(?:um)? karar\w*",
    r"bayil\w*",
    r"bayginl\w*",
    r"kalbim\w*",
    r"kalp (?:agri|krizi|sikis)\w*",
    r"carpinti\w*",
    r"nefes(?:im)? (?:alam|darl)\w*",
    r"hasta\w*",
    r"ates\w*",
    r"grip\w*",
    r"nezle\w*",
    r"mide\w* bulan\w*",
    r"kus(?:tum|uyorum|ma)\w*",
    r"migren\w*",
    r"doktor\w*",
    r"acil\w*",
    # English
    r"pain\w*",
    r"hurt\w*",
    r"injur\w*",
    r"sprain\w*",
    r"strain\w*",
    r"torn\b",
    r"tear\b",
    r"fractur\w*",
    r"dizz\w*",
    r"faint\w*",
    r"chest (?:pain|hurts|tight)\w*",
    r"heart (?:attack|pain|racing)\w*",
    r"palpitat\w*",
    r"short of breath",
    r"sick\w*",
    r"ill\b",
    r"illness\w*",
    r"fever\w*",
    r"flu\b",
    r"nause\w*",
    r"vomit\w*",
    r"migraine\w*",
)


def mentions_pain(text: str) -> bool:
    """True when the message talks about pain, injury or illness: never roast, never push."""
    return PAIN.search(fold(text)) is not None


# ---------------------------------------------------------------- never in any line

# Words that shame a body: never in a line, never in a generated reply.
BODY_SHAMING = _words(
    r"sisko\w*",
    r"sisman\w*",
    r"obez\w*",
    r"kilolu\w*",
    r"gobe[gk]\w*",
    r"yag(?:li|lar\w*|lan\w*)\b",
    r"cirkin\w*",
    r"hantal\w*",
    r"domuz\w*",
    r"fat\b",
    r"fatty",
    r"fatso",
    r"obese",
    r"chubby",
    r"skinny",
    r"ugly",
    r"belly",
    r"lard\w*",
)
# Neutral body words: fine in a factual answer ("top set weight"), never in a coach line,
# which roasts the effort and has no business talking about a body at all.
BODY_TOPIC = _words(
    r"kilo(?:n|nu|nuz|yu|ya|su|lar\w*)?\b",
    r"zayif\w*",
    r"vucud\w*",
    r"vucut\w*",
    r"beden\w*",
    r"gorunus\w*",
    # body weight, not the bar's: "your weight", "lose weight", "weigh in"
    r"(?:body|your|my|lose|losing|lost|gain|gaining|gained) ?weight\w*",
    r"weigh (?:in|more|less|yourself)\b",
    r"pounds?\b",
    r"body\b",
    r"bodies",
    r"appearance",
    r"looks?\b",
)
SLURS = _words(
    # sexual orientation / gender identity
    r"ibne\w*",
    r"donme\w*",
    r"travesti\w*",
    r"fag\w*",
    r"tranny",
    r"dyke\w*",
    # gender
    r"orospu\w*",
    r"kahpe\w*",
    r"fahise\w*",
    r"karilik\w*",
    r"whore\w*",
    r"slut\w*",
    r"bitch\w*",
    # disability
    r"sakat\b",
    r"ozurlu\w*",
    r"koturum\w*",
    r"geri zekal\w*",
    r"gerizekal\w*",
    r"mongol\w*",
    r"spasti\w*",
    r"retard\w*",
    r"cripple\w*",
    r"spaz\w*",
    # ethnicity / religion
    r"cingene\w*",
    r"kiro\b",
    r"gavur\w*",
    r"zenci\w*",
    r"yahudi\w*",
    r"kurt(?:ler)?\b",
    r"arap\b",
    r"suriyeli\w*",
    r"nigg\w*",
    r"kike\w*",
)
CALORIE_PUNISHMENT = _words(
    r"burn (?:it|that|them) off",
    r"work (?:it|that) off",
    r"earn (?:your|the) (?:food|meal|dinner|calories)",
    r"punish\w*",
    r"starv\w*",
    r"skip (?:a |the |your )?(?:meal|dinner|lunch|breakfast)",
    r"yakmak icin",
    r"yakman lazim",
    r"cezas\w*",
    r"ceza olarak",
    r"ac kal\w*",
    r"aclik\w*",
    r"ogun atla\w*",
    r"yeme(?:yeceksin|me lazim)?\b",
    r"kalori(?:yi)? kes\w*",
)


class Violation(StrEnum):
    BODY = "body"
    SLUR = "slur"
    CALORIE_PUNISHMENT = "calorie_punishment"


def violations(text: str, *, line: bool = True) -> list[Violation]:
    """The guardrails a text breaks (empty = fine). `line=True` for coach lines (no body talk at
    all); `line=False` for generated replies (only body shaming). Profanity never counts."""
    folded = fold(text)
    found = []
    if BODY_SHAMING.search(folded) or (line and BODY_TOPIC.search(folded)):
        found.append(Violation.BODY)
    if SLURS.search(folded):
        found.append(Violation.SLUR)
    if CALORIE_PUNISHMENT.search(folded):
        found.append(Violation.CALORIE_PUNISHMENT)
    return found


# ---------------------------------------------------------------- triggers


class Trigger(StrEnum):
    EXCUSE = "excuse"
    CRAVING = "craving"


EXCUSE = _words(
    r"canim iste(?:miyor|medi|mez)\w*",
    r"canim cek(?:miyor|medi)\w*",
    r"istemedim\b",
    r"hic canim yok",
    r"yarin yapar\w*",
    r"yarin gider\w*",
    r"yarin baslar\w*",
    r"sonra yapar\w*",
    r"bu hafta (?:gitmeyecegim|gitmicem|gitmem|yapmayacagim|yok)",
    r"bugun (?:gitmeyecegim|gitmicem|gitmem|yapmayacagim|pas|atliyorum|yok)",
    r"gitmek istemiyorum",
    r"usen\w*",
    r"vaktim yok",
    r"zamanim yok",
    r"motivasyonum yok",
    r"halim yok",
    r"yorgunum",
    r"cok yoruldum",
    r"uykum var",
    r"i don.?t feel like",
    r"not today",
    r"(?:i'?ll|i will|let'?s) (?:do it|go|train|start|lift) tomorrow",
    r"maybe tomorrow",
    r"skip(?:ping)? (?:today|the gym|training|the workout)",
    r"too tired",
    r"no time",
)
CRAVING = _words(
    r"canim (?:tatli|cikolata|pizza|hamburger|burger|dondurma|cips|kola|baklava)\w* cek\w*",
    r"(?:tatli|cikolata|pizza|hamburger|burger|dondurma|cips|baklava|abur cubur)\w* "
    r"(?:yiyece\w*|yicem|yiyorum|yedim|istiyorum|cekti)",
    r"abur cubur",
    r"craving\w*",
    r"junk food",
    r"(?:pizza|burger|ice cream|chocolate|candy|chips) (?:tonight|now)",
)


def excuse_kind(text: str) -> Trigger | None:
    """The savage trigger in a chat message, or None. Callers check `mentions_pain` first."""
    folded = fold(text)
    if CRAVING.search(folded):
        return Trigger.CRAVING
    if EXCUSE.search(folded):
        return Trigger.EXCUSE
    return None
