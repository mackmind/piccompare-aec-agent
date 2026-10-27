from __future__ import annotations

from factories import candidate, defaults, fake_meta_client

from aec.critic import Critic
from aec.models import ElementMatch, MeasurementDelta


def test_critic_rejects_unsupported_finding() -> None:
    critic = Critic(fake_meta_client({"decisions": []}))
    result = critic.verify(
        [candidate("room_resized", evidence_refs=[])],
        measurements=[],
        matches=[],
        evidence={},
        spec=defaults(),
    )
    assert result[0].status == "rejected"


def test_critic_refuses_definition_mismatch() -> None:
    critic = Critic(fake_meta_client({"decisions": []}))
    result = critic.verify(
        [candidate("room_split", evidence_refs=["m1"])],
        measurements=[],
        matches=[],
        evidence={},
        spec=defaults(),
    )
    assert result[0].status == "not_compared"


def test_critic_accepts_supported_finding() -> None:
    critic = Critic(
        fake_meta_client(
            {
                "decisions": [
                    {
                        "finding_id": "f1",
                        "status": "verified",
                        "reasons": ["measurement supports it"],
                        "evidence_refs": ["m1"],
                    }
                ]
            }
        )
    )
    result = critic.verify(
        [candidate("room_resized", evidence_refs=["m1"])],
        measurements=[
            MeasurementDelta(
                element_id="e1",
                status="comparable",
                area_delta_m2=2.0,
                segment_deltas_px=[20.0],
                angle_deltas_deg=[0.0],
                reasons=["area_delta"],
            )
        ],
        matches=[
            ElementMatch(
                a_id="e1",
                b_id="e2",
                status="matched",
                iou=0.9,
                centroid_delta_px=1.0,
                area_ratio=0.9,
                reasons=[],
            )
        ],
        evidence={"m1": "measurement"},
        spec=defaults(),
    )
    assert result[0].status == "verified"
