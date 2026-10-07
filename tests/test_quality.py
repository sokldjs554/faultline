import numpy as np
import pandas as pd
import pytest

from faultline.quality.contract import (
    coerce_days,
    flatline_runs,
    normalize_wo,
    quality_report,
    suggest_code_book,
)


def log(types, site=0, asset=1, day0=0):
    return pd.DataFrame(
        {
            "wo_id": range(len(types)),
            "site": site,
            "asset": asset,
            "created_day": [day0 + i for i in range(len(types))],
            "closed_day": [day0 + i + 1 for i in range(len(types))],
            "type_raw": types,
        }
    )


def test_lexicon_covers_common_spellings():
    out = normalize_wo(log(["긴급", " urgent ", "E", "예방", "PM", "일반", "수리", "zzz", None]))
    assert list(out["wo_kind"]) == [
        "emergency",
        "emergency",
        "emergency",
        "preventive",
        "preventive",
        "corrective",
        "corrective",
        "unknown",
        "unknown",
    ]


def test_code_book_overrides_and_is_validated():
    out = normalize_wo(
        log(["A1", "b2", "C3", "D4"]), {"a1": "emergency", "B2": "corrective", "C3": "preventive"}
    )
    assert list(out["wo_kind"]) == ["emergency", "corrective", "preventive", "unknown"]
    with pytest.raises(ValueError):
        normalize_wo(log(["A1"]), {"A1": "urgent"})


def test_missing_columns_are_reported():
    with pytest.raises(ValueError, match="필요한 열"):
        normalize_wo(log(["긴급"]).drop(columns=["asset"]))


def test_suggest_code_book_orders_by_frequency():
    sug = suggest_code_book(log(["C3"] * 10 + ["B2"] * 5 + ["A1"] * 2))
    assert (
        sug["C3"]["kind"] == "preventive"
        and sug["B2"]["kind"] == "corrective"
        and sug["A1"]["kind"] == "emergency"
    )
    assert suggest_code_book(log(["긴급", "예방"])) == {}


def test_report_counts_the_dirty_rows():
    wo = log(["긴급", "일반", "예방", "긴급", "일반"] * 20)
    wo.loc[0, "asset"] = np.nan
    wo.loc[1, "closed_day"] = -5
    wo = pd.concat([wo, wo.iloc[[2, 3]]], ignore_index=True)
    rep = quality_report(wo, None, None, None, 20)
    t = rep["total"]
    assert (
        t["exact_duplicates"] == 2
        and t["date_inverted"] == 1
        and t["missing_asset"] == 1
        and t["unknown_type"] == 0
    )


def test_report_flags_unreadable_codes_and_suggests_a_code_book():
    wo = pd.concat(
        [log(["A1", "B2", "C3"] * 30, site=0), log(["긴급", "일반", "예방"] * 30, site=1)], ignore_index=True
    )
    rep = quality_report(wo, None, None, None, 20)
    high = [i for i in rep["issues"] if i["level"] == "high"]
    assert [i["site"] for i in high] == [0] and "suggestion" in high[0]
    with_book = quality_report(
        wo, None, None, {0: {"A1": "emergency", "B2": "corrective", "C3": "preventive"}}, 20
    )
    assert with_book["total"]["unknown_type"] == 0


def test_emergency_share_outlier_sites_are_flagged():
    sites = []
    for s in range(6):
        types = ["긴급", "일반", "일반", "일반"] * 20  # 긴급 25%
        if s == 4:
            types = ["일반"] * 80  # 긴급을 안 쓴다
        if s == 5:
            types = ["긴급"] * 70 + ["일반"] * 10  # 긴급이 거의 전부
        sites.append(log(types, site=s))
    rep = quality_report(pd.concat(sites, ignore_index=True), None, None, None, 20)
    by_site = {i["site"]: i["level"] for i in rep["issues"] if "긴급 유형" in i["text"]}
    assert by_site == {4: "high", 5: "mid"}


def test_issues_are_sorted_by_severity(prep):
    rep = quality_report(prep.world.wo, prep.world.complaints, prep.world.assets, None, prep.world.cfg.weeks)
    order = [("high", "mid", "low").index(i["level"]) for i in rep["issues"]]
    assert order == sorted(order)


def test_flatline_runs():
    v = np.r_[np.arange(10), np.full(30, 5.0), np.arange(10)]
    assert flatline_runs(v, 24) == [(10, 40)] or flatline_runs(v, 24) == [(9, 40)]
    assert flatline_runs(np.arange(100.0), 24) == []


def test_coerce_days_reads_dates():
    wo = log(["긴급", "일반"]).astype({"created_day": object, "closed_day": object})
    wo["created_day"] = ["2024-03-01", "2024-03-11"]
    wo["closed_day"] = ["2024-03-02", "2024-03-12"]
    out = coerce_days(wo)
    assert list(out["created_day"]) == [0, 10] and list(out["closed_day"]) == [1, 11]
    wo["created_day"] = ["x", "y"]
    with pytest.raises(ValueError):
        coerce_days(wo)
