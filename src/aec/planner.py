"""Muse Spark planner: turn a review brief into a PlanSpec."""

from __future__ import annotations

from aec.meta import MetaClient
from aec.models import PlanSpec


class PlannerError(ValueError):
    pass


SYSTEM = (
    "You are an AEC measurement planner. Return only a JSON object matching "
    "the supplied PlanSpec schema. Do not invent measurements or files."
)


class Planner:
    def __init__(self, client: MetaClient) -> None:
        self.client = client

    def plan(self, brief: str, defaults: PlanSpec) -> PlanSpec:
        result = self.client.chat_json(
            SYSTEM,
            f"Review brief:\n{brief}\n\nDefaults:\n{defaults.model_dump_json()}",
            PlanSpec.model_json_schema(),
            schema_name="plan_spec",
        )
        try:
            return PlanSpec.model_validate(result.content)
        except Exception as error:  # pydantic ValidationError and shape errors
            raise PlannerError(f"planner returned an invalid PlanSpec: {error}") from error
