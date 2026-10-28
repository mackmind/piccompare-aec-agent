"""Critic: verify, reject or refuse candidate findings against evidence."""

from __future__ import annotations

import json
from typing import Any

from aec.meta import MetaClient
from aec.models import ElementMatch, Finding, MeasurementDelta, PlanSpec

SYSTEM = (
    "You are a verification critic for AEC measurement findings. Accept a "
    "finding only when the supplied evidence references support its claim. "
    "Never add measurements or evidence references. Return JSON only."
)

DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions"],
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["finding_id", "status", "reasons", "evidence_refs"],
                "properties": {
                    "finding_id": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": ["verified", "rejected", "not_compared"],
                    },
                    "reasons": {"type": "array", "items": {"type": "string"}},
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        }
    },
}


class CriticError(ValueError):
    pass


class Critic:
    def __init__(self, client: MetaClient) -> None:
        self.client = client

    def verify(
        self,
        candidates: list[Finding],
        measurements: list[MeasurementDelta],
        matches: list[ElementMatch],
        evidence: dict[str, Any],
        spec: PlanSpec,
    ) -> list[Finding]:
        deterministic: dict[str, Finding] = {}
        to_review: list[Finding] = []
        for candidate in candidates:
            if candidate.change_type in {"room_split", "room_merged"}:
                deterministic[candidate.finding_id] = candidate.model_copy(
                    update={
                        "status": "not_compared",
                        "reasons": [*candidate.reasons, "definition mismatch"],
                    }
                )
            elif not candidate.evidence_refs:
                deterministic[candidate.finding_id] = candidate.model_copy(
                    update={
                        "status": "rejected",
                        "reasons": [*candidate.reasons, "no evidence references"],
                    }
                )
            else:
                to_review.append(candidate)
        if not to_review:
            return [deterministic[c.finding_id] for c in candidates]

        context = {
            "findings": [c.model_dump() for c in to_review],
            "measurements": [m.model_dump() for m in measurements],
            "matches": [m.model_dump() for m in matches],
            "evidence_keys": sorted(evidence.keys()),
            "plan": spec.model_dump(),
        }
        result = self.client.chat_json(
            SYSTEM,
            json.dumps(context, ensure_ascii=True, sort_keys=True),
            DECISION_SCHEMA,
            schema_name="aec_critic",
            # Muse Spark is a reasoning model: reasoning tokens count against
            # this budget, and a big review context can exhaust it before any
            # JSON is emitted (observed live 2026-10-28: finish_reason=length,
            # content=None at 2048).
            max_tokens=8192,
        )
        decisions = result.content.get("decisions")
        if not isinstance(decisions, list):
            raise CriticError("critic response has no decisions array")
        by_id: dict[str, dict[str, Any]] = {}
        for decision in decisions:
            if not isinstance(decision, dict):
                raise CriticError("critic decision is not an object")
            finding_id = str(decision.get("finding_id", ""))
            if finding_id not in {candidate.finding_id for candidate in to_review}:
                raise CriticError(f"critic returned unknown finding id {finding_id!r}")
            by_id[finding_id] = decision

        reviewed: list[Finding] = []
        for candidate in to_review:
            decision = by_id.get(candidate.finding_id)
            if decision is None:
                reviewed.append(
                    candidate.model_copy(
                        update={"status": "rejected", "reasons": ["critic omitted finding"]}
                    )
                )
                continue
            status = decision.get("status")
            if status not in {"verified", "rejected", "not_compared"}:
                raise CriticError(f"invalid critic status {status!r}")
            refs = decision.get("evidence_refs", [])
            if not isinstance(refs, list) or not set(refs).issubset(
                set(candidate.evidence_refs)
            ):
                reviewed.append(
                    candidate.model_copy(
                        update={
                            "status": "rejected",
                            "reasons": ["critic added or invented evidence"],
                        }
                    )
                )
                continue
            reasons = decision.get("reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            reviewed.append(
                candidate.model_copy(
                    update={
                        "status": status,
                        "reasons": [*candidate.reasons, *[str(r) for r in reasons]],
                    }
                )
            )
        forced = [
            deterministic[c.finding_id]
            for c in candidates
            if c.finding_id in deterministic
        ]
        return forced + reviewed


class DeterministicCritic:
    """Offline critic for fixture evaluation; no model or network call."""

    def verify(
        self,
        candidates: list[Finding],
        measurements: list[MeasurementDelta],
        matches: list[ElementMatch],
        evidence: dict[str, Any],
        spec: PlanSpec,
    ) -> list[Finding]:
        result: list[Finding] = []
        for candidate in candidates:
            if (
                candidate.change_type in {"room_split", "room_merged"}
                or candidate.status == "not_compared"
            ):
                result.append(
                    candidate.model_copy(
                        update={
                            "status": "not_compared",
                            "reasons": [*candidate.reasons, "definition mismatch"],
                        }
                    )
                )
            elif not candidate.evidence_refs:
                result.append(
                    candidate.model_copy(
                        update={
                            "status": "rejected",
                            "reasons": [*candidate.reasons, "no evidence references"],
                        }
                    )
                )
            else:
                result.append(
                    candidate.model_copy(
                        update={
                            "status": "verified",
                            "reasons": [*candidate.reasons, "deterministic offline critic"],
                        }
                    )
                )
        return result
