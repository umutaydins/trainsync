"""Savage lines for the progress summaries (P8.11, ADR 0038), merged into `savage_en` and
`savage_tr`. Gains get praise, drops a roast of the effort; never body, weight or appearance, and
a period with sick or injured days never gets a drop line (the code sends a calm one instead).
"""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from collections.abc import Mapping

from trainsync.modules.coach.categories import Category

Lines = Mapping[Category, tuple[str, ...]]

EN_LINES: Lines = {
    Category.PROGRESS_UP: (
        "More work than last time. Hell yes, keep stacking it.",
        "The numbers went up because you showed up. Again.",
        "Better than the last stretch. Don't you dare coast now.",
        "That's a real step forward. Now make it the new floor.",
        "Up across the board. Good shit, same again.",
        "You out-worked your old self. That's the only rival.",
    ),
    Category.PROGRESS_DOWN: (
        "Less work than last time. That trend ends this week.",
        "The numbers dropped. Excuses don't show up in the log.",
        "You slacked off and the record shows it. Fix that shit.",
        "Down from the last stretch. Pick the damn pace back up.",
        "The plan didn't get easier, you got lazier. Back to it.",
        "A dip is a warning shot. Answer it with a full week.",
    ),
}
EN_MAX: Lines = {
    Category.PROGRESS_UP: (
        "Holy shit, more work than last time. Keep fucking going.",
        "Damn, the numbers climbed. Hell of a stretch.",
        "Up again, goddamn it. That's how the fuck it's done.",
        "Shit, you actually out-worked yourself. Respect.",
        "Hell yes, more volume. Stack it, damn it.",
        "Fucking solid stretch. Now do it again.",
    ),
    Category.PROGRESS_DOWN: (
        "What the fuck happened? Less work than last time.",
        "Damn, the numbers sank. Get your shit together.",
        "Slacked off as hell. The log doesn't lie, goddamn it.",
        "Shit stretch. Next one, full fucking effort.",
        "Hell no, this is not the pace. Pick it the fuck up.",
        "Down again? Bullshit. Show up and fix it.",
    ),
}
TR_LINES: Lines = {
    Category.PROGRESS_UP: (
        "Geçen döneme göre daha çok iş. Aferin lan, böyle devam.",
        "Rakamlar yükseldi çünkü sen geldin. Bırakmak yok.",
        "Bir adım önde. Şimdi bunu yeni taban yap.",
        "Eski halini geçtin. Tek rakibin o, onu da geçiyorsun.",
        "Her yerde artış. Hassiktir, temiz iş, aynısı tekrar.",
        "Emek konuştu. Gevşemek yok, devam.",
    ),
    Category.PROGRESS_DOWN: (
        "Geçen döneme göre az iş. Bu gidişat bu hafta bitiyor.",
        "Rakamlar düştü. Bahane kayıtta görünmüyor, setler görünüyor.",
        "Gevşedin ve kayıt bunu gösteriyor. Siktir et bahaneyi, düzelt.",
        "Tempo düştü ulan. Toparla.",
        "Program kolaylaşmadı, sen tembelleştin. Geri dön.",
        "Bu düşüş bir uyarı. Cevabı tam bir hafta olsun.",
    ),
}
TR_MAX: Lines = {
    Category.PROGRESS_UP: (
        "Hassiktir, geçen dönemden fazla iş! Devam lan.",
        "Amına koyayım, rakamlar uçtu. Helal amk.",
        "Siktir, yine artış. İşte böyle yapılır lan.",
        "Ulan eski halini geçtin. Saygı amk.",
        "Amk, hacim arttı. Üstüne koy, bırakma.",
        "Sikeyim, sağlam dönem. Şimdi tekrar et.",
    ),
    Category.PROGRESS_DOWN: (
        "Amına koyayım, ne oldu? Geçen dönemden az iş.",
        "Siktir, rakamlar dibe vurdu. Toparlan lan.",
        "Ulan gevşedin, kayıt yalan söylemez amk.",
        "Bok gibi dönem amk. Sıradaki tam olacak.",
        "Hassiktir, bu tempo değil. Hızlan lan.",
        "Yine mi düşüş? Siktir et bahaneyi, gel düzelt.",
    ),
}
