"""The OpenAPI examples of /v1/stats are valid responses."""

from typing import Any

import pytest
from pydantic import BaseModel

from trainsync.modules.stats.schemas import HeatmapOut, PrsOut, SeriesOut
from trainsync.modules.stats.totals import ActivitySummary, StatsSummary, WeeklyStats


@pytest.mark.parametrize(
    "model", [StatsSummary, ActivitySummary, WeeklyStats, SeriesOut, HeatmapOut, PrsOut]
)
def test_the_example_validates(model: type[BaseModel]) -> None:
    extra: Any = model.model_config.get("json_schema_extra")
    (example,) = extra["examples"]
    model.model_validate(example)
