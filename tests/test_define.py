import numpy as np
import pandas as pd
import pytest

from faultline.define import spec
from faultline.define.engine import apply_definition

ASSETS = pd.DataFrame(
    {
        "asset": [1, 2, 3],
        "site": [0, 0, 0],
        "category": ["chiller", "pump", "elevator"],
        "floor": [-1, 3, 5],
    }
)
EMPTY_CMP = pd.DataFrame(columns=["complaint_id", "site", "floor", "day", "symptom", "hint_asset", "text"])


def wo(rows):
    df = pd.DataFrame(rows, columns=["wo_id", "site", "asset", "created_day", "wo_kind"])
    df["closed_day"] = df["created_day"] + 1
    df["type_raw"] = df["wo_kind"]
    return df


def cmp(rows):
    df = pd.DataFrame(rows, columns=["site", "floor", "day", "symptom", "hint_asset"])
    df.insert(0, "complaint_id", range(len(df)))
    df["text"] = ""
    return df


def test_all_builtin_definitions_load_and_roundtrip():
    defs = spec.builtin()
    assert len(defs) == 6
    for name, d in defs.items():
        assert d.name == name
        assert spec.Definition.from_dict(d.to_dict()) == d
        assert spec.load_text(spec.builtin_text(name)) == d


@pytest.mark.parametrize(
    "text",
    [
        "name: x\nwo:\n  kinds: [preventive]\n",
        "name: x\nwo:\n  kinds: [emergency]\n  require: always\n",
        "name: x\nwo:\n  kinds: [emergency]\nevent_time: tomorrow\n",
        "wo:\n  kinds: [emergency]\n",
        "a: [1",
        "- 1\n- 2\n",
        "name: x\nwo: 3\n",
        "name: x\nwo:\n  kinds: [emergency]\ncomplaints:\n  support_window_days: [5, 1]\n",
        "name: x\nwo:\n  kinds: [emergency]\nmerge_window_days: -1\n",
    ],
)
def test_bad_definitions_raise_value_error(text):
    with pytest.raises(ValueError):
        spec.load_text(text)


def test_emergency_only_vs_all_corrective():
    log = wo([(1, 0, 1, 10, "emergency"), (2, 0, 2, 40, "corrective"), (3, 0, 3, 60, "preventive")])
    d = spec.builtin()
    r1 = apply_definition(d["d1_emergency"], log, EMPTY_CMP, ASSETS).incidents
    r2 = apply_definition(d["d2_corrective"], log, EMPTY_CMP, ASSETS).incidents
    assert list(r1["asset"]) == [1]
    assert sorted(r2["asset"]) == [1, 2]


def test_complaint_support_decides_corrective_wo():
    # 펌프(자산 2, 3층)의 시정 작업지시. 같은 증상의 민원이 3층에서 들어오면 d3 는 고장으로 본다.
    log = wo([(1, 0, 2, 20, "corrective")])
    supported = cmp([(0, 3, 18, "누수", np.nan)])
    other_floor = cmp([(0, 7, 18, "누수", np.nan)])
    wrong_symptom = cmp([(0, 3, 18, "정전", np.nan)])
    too_late = cmp([(0, 3, 60, "누수", np.nan)])
    d3 = spec.builtin()["d3_corroborated"]
    assert len(apply_definition(d3, log, supported, ASSETS).incidents) == 1
    for c in (other_floor, wrong_symptom, too_late, EMPTY_CMP):
        assert apply_definition(d3, log, c, ASSETS).incidents.empty


def test_event_time_uses_earliest_evidence():
    log = wo([(1, 0, 2, 20, "emergency")])
    c = cmp([(0, 3, 17, "누수", np.nan)])
    d3 = spec.builtin()["d3_corroborated"]
    d6 = spec.builtin()["d6_corroborated_first_record"]
    assert int(apply_definition(d3, log, c, ASSETS).incidents["day"].iloc[0]) == 17
    assert int(apply_definition(d6, log, c, ASSETS).incidents["day"].iloc[0]) == 20


def test_complaint_cluster_becomes_incident_without_a_work_order():
    d3 = spec.builtin()["d3_corroborated"]
    c = cmp([(0, 5, 30, "갇힘", np.nan), (0, 5, 31, "갇힘", np.nan), (0, 5, 33, "갇힘", np.nan)])
    res = apply_definition(d3, wo([]), c, ASSETS)
    inc = res.incidents
    assert list(inc["asset"]) == [3] and inc["evidence"].iloc[0] == "complaint"


def test_cluster_that_cannot_name_one_asset_is_counted_not_guessed():
    d3 = spec.builtin()["d3_corroborated"]
    assets = pd.concat(
        [ASSETS, pd.DataFrame({"asset": [4], "site": [0], "category": ["pump"], "floor": [3]})],
        ignore_index=True,
    )
    c = cmp([(0, 3, 30, "누수", np.nan), (0, 3, 31, "누수", np.nan), (0, 3, 32, "누수", np.nan)])
    res = apply_definition(d3, wo([]), c, assets)
    assert res.incidents.empty and res.stats["unresolved_clusters"] == 1


def test_merge_window():
    log = wo([(1, 0, 1, 10, "emergency"), (2, 0, 1, 16, "emergency"), (3, 0, 1, 30, "emergency")])
    d1 = spec.builtin()["d1_emergency"]  # 병합 7일: 10·16일은 한 사건, 30일은 따로
    assert len(apply_definition(d1, log, EMPTY_CMP, ASSETS).incidents) == 2
    d5 = spec.builtin()["d5_emergency_loose"]  # 병합 21일
    assert len(apply_definition(d5, log, EMPTY_CMP, ASSETS).incidents) == 1


def test_as_of_day_hides_later_records():
    log = wo([(1, 0, 1, 10, "emergency"), (2, 0, 2, 100, "emergency")])
    d1 = spec.builtin()["d1_emergency"]
    assert len(apply_definition(d1, log, EMPTY_CMP, ASSETS, as_of_day=50).incidents) == 1
    assert len(apply_definition(d1, log, EMPTY_CMP, ASSETS).incidents) == 2


def test_missing_asset_and_duplicates_are_not_incidents():
    log = wo([(1, 0, np.nan, 10, "emergency"), (2, 0, 1, 20, "emergency"), (2, 0, 1, 20, "emergency")])
    res = apply_definition(spec.builtin()["d1_emergency"], log, EMPTY_CMP, ASSETS)
    assert len(res.incidents) == 1 and res.stats["wo_missing_asset"] == 1
