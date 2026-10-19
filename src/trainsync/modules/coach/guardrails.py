"""Hard guardrails of the coach (ADR 0030, 0032): the only limits that also hold in savage and
in max profanity.

- `mentions_distress`: guilt spiral, throwing up, not eating, self-hate, binge talk → a calm
  reply, no swearing, no roast (checked first).
- `mentions_pain`: pain, injury, illness, dizziness, chest pain and the like → no roast, no push.
- `violations`: body/weight/appearance words, identity slurs (ethnicity, religion, sexual
  orientation, disability, gender) and calorie-punishment or restriction phrases. Profanity is
  not on the list and is never filtered.
- `excuse_kind` / `food_kind`: the excuse and unhealthy-choice phrases that trigger the savage
  replies.

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
    r"(?:belim|boynum|sirtim|bacagim|kasim|baldirim) tut\w*",
    r"kramp\w*",
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
    # "acil" (emergency), "acile", "acilde"; not "acildi" ("opened", folded)
    r"acil(?:e|de|den|i|in)?\b",
    # English
    r"pain\w*",
    r"hurt\w*",
    r"injur\w*",
    r"sprain\w*",
    r"pull(?:ed)? (?:a |my )?(?:muscle|hamstring|groin|calf|back)\w*",
    r"cramp\w*",
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


# ---------------------------------------------------------------- distress (ADR 0032)

DISTRESS = _words(
    # guilt spiral (Turkish, folded)
    r"kendimi suclu hiss\w*",
    r"cok sucluyum",
    r"sucluluk\w*",
    r"vicdan azab\w*",
    r"yedigim(?:e|den) pisman\w*",
    r"her seyi mahvett\w*",
    r"kendimden igren\w*",
    # threw up / purging
    r"kustum",
    r"kusturdum",
    r"kendimi kustur\w*",
    r"kusmak istiyorum",
    r"parmak att\w*",
    # not eating
    r"(?:bugun )?(?:hic ?bir sey|hic) yemedim",
    r"sabahtan beri (?:bir sey |hic )?yemedim",
    r"gunlerdir (?:bir sey )?yemiyorum",
    r"yemek yemiyorum",
    r"ac kaldim",
    # self-hate
    r"kendimden nefret\w*",
    r"kendimi sevmiyorum",
    r"berbat biriyim",
    r"degersizim",
    r"ise yaramazin\w*",
    r"olmek istiyorum",
    r"kendimi oldur\w*",
    r"intihar\w*",
    # binge talk
    r"tikin\w*",
    r"kendimi durduramad\w*",
    r"durduramadim",
    r"kontrolu kaybett\w*",
    r"bir oturusta (?:hepsini|butun)\w*",
    # English
    r"(?:feel|feeling|felt) (?:so |really |very )?guilty",
    r"guilt\w*",
    r"ashamed",
    r"disgusted (?:with|by) myself",
    r"ruined everything",
    r"threw up",
    r"throw(?:ing)? up",
    r"made myself (?:sick|throw up|vomit)",
    r"purg\w*",
    r"haven'?t eaten",
    r"have not eaten",
    r"didn'?t eat (?:anything|all day|today)",
    r"not eating",
    r"starving myself",
    r"hate myself",
    r"i'?m (?:worthless|disgusting|useless)",
    r"want to die",
    r"kill myself",
    r"suicid\w*",
    r"self.?harm\w*",
    r"binge\w*",
    r"bingi\w*",
    r"couldn'?t stop eating",
    r"lost control",
)


def mentions_distress(text: str) -> bool:
    """True for guilt, purging, not eating, self-hate or binge talk: a calm reply only, never a
    roast and never a swear word, whatever the intensity and profanity (ADR 0032)."""
    return DISTRESS.search(fold(text)) is not None


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
    # ADR 0032: never eat below the target, never compensate with cardio
    r"eat(?:ing)? less\b",
    r"eat(?:ing)? below",
    r"below (?:your|the) (?:kcal |calorie )?target",
    r"make up for (?:it|that) (?:with|by)",
    r"(?:extra|more) cardio (?:to|for)",
    r"daha az ye\b",
    r"az ye\b",
    r"(?:kalori|kcal) hedef\w* altin\w*",
    r"kardiyo(?:yla| ile) (?:yak|telafi)\w*",
    r"telafi (?:et|icin)\w*",
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
    FOOD = "food"


class FoodKind(StrEnum):
    """What the unhealthy choice is about: picks the one concrete move (ADR 0032)."""

    SWEET = "sweet"
    FAST_FOOD = "fast_food"
    FRIED = "fried"
    ALCOHOL = "alcohol"
    SMOKING = "smoking"
    LATE = "late"


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
FOOD: dict[FoodKind, re.Pattern[str]] = {
    FoodKind.SWEET: _words(
        r"baklava\w*",
        r"kunefe\w*",
        r"tatli(?:lar|lari|yi|ya|ci|cik)?\b",
        r"cikolata\w*",
        r"dondurma\w*",
        r"kurabiye\w*",
        r"gofret\w*",
        r"lokum\w*",
        r"seker(?:leme|lemeler|li)?\b",
        r"kek(?:i|ler)?\b",
        r"pasta(?:yi|ya|si|lar\w*|ne\w*)\b",
        r"(?:coca )?kola(?:yi|ya|lar)?\b",
        r"gazli icecek\w*",
        r"enerji icece\w*",
        r"red ?bull\w*",
        r"dessert\w*",
        r"chocolate\w*",
        r"candy",
        r"sweets",
        r"cake\w*",
        r"cookie\w*",
        r"donut\w*",
        r"doughnut\w*",
        r"ice cream",
        r"soda\b",
        r"coke\b",
        r"cola\b",
        r"energy drink\w*",
        r"sugar\w*",
    ),
    FoodKind.FAST_FOOD: _words(
        r"hamburger\w*",
        r"burger\w*",
        r"pizza\w*",
        r"doner(?:ci|e|i)?\b",
        r"durum(?:cu|e|u)?\b",
        r"fast ?food\w*",
        r"mcdonald\w*",
        r"burger king",
        r"kfc\b",
        r"nugget\w*",
        r"hot ?dog\w*",
        r"abur cubur",
        r"junk food",
        r"takeaway",
    ),
    FoodKind.FRIED: _words(
        r"kizartma\w*",
        r"kizarmis\w*",
        r"cips\w*",
        r"chips\b",
        r"fries\b",
        r"fried\b",
        r"deep.?fr\w*",
    ),
    FoodKind.ALCOHOL: _words(
        r"bira(?:yi|ya|lar\w*|cigim|cagim)?\b",
        r"raki(?:yi|ya)?\b",
        r"sarap\w*",
        r"alkol\w*",
        r"votka\w*",
        r"viski\w*",
        r"sarhos\w*",
        r"beer\w*",
        r"wine\b",
        r"vodka\w*",
        r"whisk(?:e)?y\w*",
        r"alcohol\w*",
        r"drunk\b",
        r"shots\b",
        r"cocktail\w*",
        r"tequila\w*",
    ),
    FoodKind.SMOKING: _words(
        r"sigara\w*",
        r"nargile\w*",
        r"vape\w*",
        r"vaping",
        r"cigarette\w*",
        r"smok(?:e|es|ed|ing)\b",
    ),
    FoodKind.LATE: _words(
        r"gec yat\w*",
        r"sabaha kadar",
        r"uyumadim",
        r"uykusuz\w*",
        r"gece (?:[1-4]|bir|iki|uc|dort)(?:te|de|e|ye)?\b",
        r"stay(?:ing|ed)? up late",
        r"up (?:all night|late)",
        r"all.?nighter",
        r"didn'?t sleep",
        r"no sleep",
    ),
}


def food_kind(text: str) -> FoodKind | None:
    """The unhealthy choice a chat message talks about, or None. Callers check
    `mentions_distress` and `mentions_pain` first."""
    folded = fold(text)
    return next((kind for kind, pattern in FOOD.items() if pattern.search(folded)), None)


def excuse_kind(text: str) -> Trigger | None:
    """The savage trigger in a chat message, or None. Callers check `mentions_distress` and
    `mentions_pain` first."""
    if food_kind(text) is not None:
        return Trigger.FOOD
    if EXCUSE.search(fold(text)):
        return Trigger.EXCUSE
    return None
