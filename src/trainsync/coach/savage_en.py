"""The savage English pack (BOT_INTENSITY=savage, BOT_LANG=en or `/lang en`; ADR 0030, 0031):
original lines, per category, the same categories as `savage_tr`.

The owner opted into unrestricted profanity, in English too. The lines roast the excuse or the
effort only: never body, weight or appearance, never identity, never food or eating, never a push
through pain (tests/unit/test_coach_lines.py checks the guardrail blocklist). Lines carry no
numbers: the facts go in a separate line the code writes. No line quotes or imitates a real person.
"""

from collections.abc import Mapping

from trainsync.coach.categories import Category
from trainsync.coach.punchlines import PUNCHLINES

LINES: Mapping[Category, tuple[str, ...]] = {
    Category.EXCUSE: (
        "You don't feel like it? Fuck your feelings, they never lifted a single plate.",
        '"Tomorrow" is a goddamn fairy tale. Today is the only day on the schedule.',
        "That excuse is bullshit and you know it. Shoes on.",
        "Skipping the week? Like hell you are. Bag, door, gym.",
        "Tired? Tired is the job description, not a way out of it.",
        "The voice in your head that says skip it is a lying piece of shit. Ignore it.",
        "Stop waiting for motivation. Discipline doesn't give a damn about your mood.",
        "Every excuse is a set you owe me. I'm keeping the tab.",
    ),
    Category.MISSED_WORKOUT: (
        "You skipped it. Congratulations, you fucked over the only person who's counting on you.",
        "Missed session. No double tomorrow, no drama. Just show the fuck up.",
        "Another day off the plan. The plan didn't skip you, you skipped it.",
        "That workout didn't happen and no story changes that shit.",
        "You ghosted the gym. It noticed. So did I.",
        "One missed day is a slip. Two is a habit. Don't you dare make it two.",
        "Hell of a way to waste a training day.",
    ),
    Category.UNDER_TARGET: (
        "That's short of the plan. Next set, hit the damn number.",
        "Under target. Half-assed reps don't count as reps.",
        "You've lifted more than that before. Stop holding back, for fuck's sake.",
        "Short again. The plan wasn't a suggestion.",
        "That set was weak as hell. Reset and do it right.",
        "Close isn't the target. The target is the target.",
        "Not good enough and you know it. Fix it on the next one.",
    ),
    Category.WORKOUT_START: (
        "Finally. Now shut up and lift.",
        "We're on. No phone, no chatter, just work.",
        "Started. Good. Now make it count, damn it.",
        "You showed up. That's the floor, not the ceiling. Go.",
        "Clock's running. Don't waste a second of this shit.",
        "Here we go. Every set by the plan, no shortcuts.",
        "You're in. Leave the excuses in the fucking locker.",
    ),
    Category.REST_OVER: (
        "Rest's over. Up. Next set.",
        "Break's done. Get your ass back under the bar.",
        "Time. Stop scrolling and lift.",
        "That's enough rest. Move.",
        "Up. The next set isn't going to do itself.",
        "Rest time's gone. So is your excuse. Go.",
        "Get up, damn it. Next set.",
    ),
    Category.WORKOUT_DONE_GOOD: (
        "Every set done. Hell yes. That's how it's done.",
        "Clean session. Don't get cocky, do it again next time.",
        "Plan done, nothing skipped. Fucking solid.",
        "That's the work. No excuses today, and it shows.",
        "Good shit. Now recover and come back hungry.",
        "Nothing left on the table. Respect.",
    ),
    Category.WORKOUT_DONE_BAD: (
        "Half a workout. Half the result. Do the math.",
        "You left sets on the table. That shit adds up.",
        "Ended early. The plan wasn't finished, you just quit on it.",
        "That was a sloppy session. Next time, every set, no bullshit.",
        "You walked out before the work was done. Not good enough.",
        "Missed sets don't vanish. They show up in your results.",
    ),
    Category.REMINDER_BEFORE: (
        "Half an hour. Get your shit together and go.",
        "Training's coming up. Start moving now, not later.",
        "Bag packed? Shoes on? No? Fix that, now.",
        "Thirty minutes to stop making excuses. Use them well.",
        "Session soon. Don't even think about bailing.",
        "Get ready. Today's not a day off.",
    ),
    Category.REMINDER_NOW: (
        "It's time. Move your ass.",
        "Now. Not in five minutes. Now.",
        "Start time. Every minute you wait is a minute you wasted.",
        "Go. The plan says now, so it's fucking now.",
        "Time's up for thinking about it. Go train.",
        "This is the hour. Get in there.",
    ),
    Category.ESCALATION: (
        "Still nothing? What the fuck are you waiting for?",
        "Half an hour late and counting. Get up.",
        "You're still not training. That couch isn't your coach.",
        "I'm not going away. Neither is the workout. Go.",
        "Late as hell already. Late beats never. Move.",
        "Every minute you stall makes it harder. Quit stalling.",
        "Do I need to spell it out? Train. Now. Damn it.",
    ),
    Category.LANGUAGE_SET: (
        "English it is. New language, same rules: no fucking excuses.",
        "Switched to English. Now you'll understand every word of the roast.",
        "English now. The words changed, the work didn't.",
        "Fine, English. Doesn't make the sets any lighter.",
        "English, done. Excuses sound just as shitty in this language.",
    ),
    Category.PUNCHLINE_EN: PUNCHLINES,
}
