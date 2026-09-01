from __future__ import annotations

import pytest

from aegis.intel.short_horizon_policy import (
    build_feature_provenance,
    validate_feature_provenance,
)


def test_feature_provenance_attests_every_feature_at_decision_time():
    names = [
        "bid",
        "return_60s",
        "symbol_bucket_00",
        "mechanism_bucket_31",
        "horizon_s",
    ]

    provenance = build_feature_provenance(names)
    validate_feature_provenance(provenance, names)

    assert provenance["schema"] == "point_in_time_feature_provenance.v1"
    assert provenance["all_features_available_at_or_before_decision"] is True
    assert set(provenance["features"]) == set(names)
    assert all(
        row["availability"] == "at_or_before_decision"
        for row in provenance["features"].values()
    )


def test_feature_provenance_rejects_unknown_or_future_alias():
    with pytest.raises(ValueError, match="future outcome alias"):
        build_feature_provenance(["time_to_first_net_green"])

    with pytest.raises(ValueError, match="unknown point-in-time feature"):
        build_feature_provenance(["unattested_feature"])


def test_feature_provenance_rejects_missing_attestation_row():
    provenance = build_feature_provenance(["bid", "ask"])
    del provenance["features"]["ask"]

    with pytest.raises(ValueError, match="feature rows do not match"):
        validate_feature_provenance(provenance, ["bid", "ask"])
