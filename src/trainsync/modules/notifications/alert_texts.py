"""Stack alert texts, in the chat's language (`/lang`, ADR 0031); tone-free, like the neutral
layer. Kept here rather than in the coach packs: they are operator messages, not coaching."""

# Turkish text: the dotless i (U+0131) is a letter here, not a confusable.
# ruff: noqa: RUF001

from collections.abc import Mapping
from datetime import datetime

from trainsync.core.settings import BotLang
from trainsync.modules.notifications.alert_conditions import (
    SECONDS_PER_MINUTE,
    Action,
    AlertState,
    Detail,
    Observation,
)

DETAILS: Mapping[BotLang, Mapping[Detail, str]] = {
    "en": {
        Detail.CIRCUIT_UNKNOWN: "no circuit breaker state reported",
        Detail.CIRCUIT_CLOSED: "Strava circuit breaker is closed again",
        Detail.CIRCUIT_OPEN: "Strava circuit breaker {state}, not closed for {minutes}+ min",
        Detail.DEAD_LETTERS: "{count} dead-letter webhook event(s), failed {attempts} times "
        "and no longer retried (GET /v1/sync/status)",
        Detail.DEAD_LETTERS_NONE: "no dead-letter webhook events left",
        Detail.NO_ATHLETE: "no athlete connected",
        Detail.NEVER_SYNCED: "never synced yet",
        Detail.SYNC_STALE: "no successful sync for {hours:.1f} h (last {last})",
        Detail.SYNC_OK: "syncing again (last {last})",
        Detail.NO_BACKUP: "no backup in {directory}",
        Detail.BACKUP_STALE: "newest backup is {hours:.1f} h old ({name})",
        Detail.BACKUP_OK: "a fresh backup exists ({name})",
    },
    "tr": {
        Detail.CIRCUIT_UNKNOWN: "devre kesici durumu bildirilmedi",
        Detail.CIRCUIT_CLOSED: "Strava devre kesicisi yeniden kapandı",
        Detail.CIRCUIT_OPEN: "Strava devre kesicisi {state}, {minutes}+ dk kapanmadı",
        Detail.DEAD_LETTERS: "{count} dead-letter webhook olayı {attempts} kez başarısız oldu "
        "ve artık denenmiyor (GET /v1/sync/status)",
        Detail.DEAD_LETTERS_NONE: "dead-letter webhook olayı kalmadı",
        Detail.NO_ATHLETE: "bağlı sporcu yok",
        Detail.NEVER_SYNCED: "henüz hiç senkronize edilmedi",
        Detail.SYNC_STALE: "{hours:.1f} sa boyunca başarılı senkronizasyon yok (son {last})",
        Detail.SYNC_OK: "senkronizasyon yeniden çalışıyor (son {last})",
        Detail.NO_BACKUP: "{directory} içinde yedek yok",
        Detail.BACKUP_STALE: "en yeni yedek {hours:.1f} sa önce alınmış ({name})",
        Detail.BACKUP_OK: "yeni bir yedek var ({name})",
    },
}
HEADLINES: Mapping[BotLang, Mapping[Action, str]] = {
    "en": {
        Action.FIRE: "trainsync alert: {detail}",
        Action.RESOLVE: "trainsync resolved: {detail}",
    },
    "tr": {
        Action.FIRE: "trainsync uyarısı: {detail}",
        Action.RESOLVE: "trainsync düzeldi: {detail}",
    },
}
AFTER: Mapping[BotLang, str] = {"en": " (after {minutes} min)", "tr": " ({minutes} dk sonra)"}


def message(
    action: Action, observation: Observation, old: AlertState, now: datetime, lang: BotLang = "en"
) -> str:
    detail = DETAILS[lang][observation.detail].format(**observation.fields)
    text = HEADLINES[lang][action].format(detail=detail)
    if action is Action.RESOLVE and old.bad_since is not None:
        minutes = max(0, int((now - old.bad_since).total_seconds() // SECONDS_PER_MINUTE))
        text += AFTER[lang].format(minutes=minutes)
    return text
