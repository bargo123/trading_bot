from __future__ import annotations

from aegis.research.firehose_mechanisms import built_in_mechanisms


def test_ponsi_failed_breakout_spec_has_source_and_falsification():
    spec = built_in_mechanisms()["failed_breakout_fade_v1"]

    assert spec.source_kind == "BOOK_DERIVED"
    assert spec.passage_hashes
    assert spec.falsification
