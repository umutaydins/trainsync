"""Every model module, so `Base.metadata` knows all tables (Alembic, `create_all`, FK targets).

Import `Base` from here, not from `trainsync.core.orm`, wherever the whole schema matters.
"""

from trainsync.core.orm import Base
from trainsync.modules.activities import models as activities
from trainsync.modules.chat import models as chat
from trainsync.modules.checkin import models as checkin
from trainsync.modules.notifications import models as notifications
from trainsync.modules.nutrition import models as nutrition
from trainsync.modules.strava import models as strava
from trainsync.modules.sync import models as sync
from trainsync.modules.training import models as training

MODEL_MODULES = (activities, chat, checkin, notifications, nutrition, strava, sync, training)

__all__ = ["MODEL_MODULES", "Base"]
