"""커밋된 산출물이 문서가 말하는 내용과 어긋나지 않는지 본다. 실험을 다시 돌려 숫자가 바뀌어도 서술이 맞는지 확인하는 안전장치다."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def load(name):
    p = ROOT / "artifacts" / f"{name}.json"
    if not p.exists():
        pytest.skip(f"{name}.json 이 없다 (make pipeline)")
    return json.loads(p.read_text())


def test_summary_is_derived_from_the_other_artifacts():
    from faultline.eval import summary as S
    from run_all import _jsonable

    base, multi = load("base"), load("multiseed")
    rebuilt = _jsonable(S.build_summary(base, multi, load("drift"), load("validity"), load("robustness")))
    assert rebuilt == load("summary")


def test_headline_claims_hold():
    s = load("summary")
    n = s["worlds"]["base_seeds"]
    assert s["auc"]["d2_beats_d1_seeds"] == n  # 문서: 모든 시드에서 d2 가 d1 보다 높다
    assert (
        s["apparent"]["best_by_own_is_best_by_truth"] == 0
    )  # 문서: 자기 라벨의 1위가 진짜 1위인 시드는 없다
    assert s["apparent"]["d1_own_auc"] > s["apparent"]["d2_own_auc"]
    assert s["apparent"]["d1_truth_auc"] < s["apparent"]["d2_truth_auc"]
    assert s["auc"]["spread_uniform"] < s["auc"]["spread"]  # 습관이 같은 세계에서는 정의 차이가 작다
    assert s["labels"]["d1_recall_no_emergency_sites"] < 0.1 < s["labels"]["d1_recall_standard_sites"]
    assert all(v["d2_minus_d1"] > 0 for v in s["robustness"].values())


def test_honest_negative_results_are_still_true():
    s = load("summary")
    c = s["customization"]
    assert c["audit_80"] <= c["fixed_d2"] + 1e-9  # 문서: 사이트별 선택은 고정 d2 를 넘지 못했다
    assert abs(s["maturity"]["mature_minus_current"]) < 0.01  # 문서: 라벨 성숙은 학습에 영향이 거의 없다
    assert s["audit"]["n_for_90pct"] is None  # 문서: 320건으로도 90% 에 못 미친다
    d = s["drift"]
    assert d["detected"] < d["shifts"]  # 문서: 놓친 변화가 있다
    assert d["false_alarm_site_runs"] / d["quiet_site_runs"] < 0.05


def test_audit_curve_improves_with_more_checks():
    a = load("multiseed")["base"]["audit"]
    assert a["regret"][0] > a["regret"][-1] and a["p_near"][0] < a["p_near"][-1]


def test_manifest_matches_protocol():
    from faultline.eval import protocol as P

    m = load("manifest")
    assert m["protocol"]["topk"] == P.TOPK and m["protocol"]["cutoff_week"] == P.CUTOFF_WEEK
    assert set(m["definitions"]) == {
        "d1_emergency",
        "d2_corrective",
        "d3_corroborated",
        "d4_complaint_confirmed",
        "d5_emergency_loose",
        "d6_corroborated_first_record",
    }
