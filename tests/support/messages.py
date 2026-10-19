"""The default message pack (BOT_TONE=neutral, BOT_LANG=en) for tests of the bot's wording."""

from trainsync.modules.coach.packs import PACKS, Messages

NEUTRAL_EN = Messages(PACKS["neutral", "en"])
