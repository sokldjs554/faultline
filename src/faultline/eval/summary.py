"""여러 시드의 실험 결과를 합치고, 문서와 콘솔이 쓰는 대표 숫자를 뽑는다."""

from __future__ import annotations

import numpy as np

DEFS = (
    "d1_emergency",
    "d2_corrective",
    "d3_corroborated",
    "d4_complaint_confirmed",
    "d5_emergency_loose",
    "d6_corroborated_first_record",
)


def _stat(vals: list[float]) -> dict:
    a = np.asarray(vals, dtype=float)
    return {
        "mean": float(np.nanmean(a)),
        "min": float(np.nanmin(a)),
        "max": float(np.nanmax(a)),
        "values": [float(x) for x in a],
    }


def aggregate_runs(runs: list[dict]) -> dict:
    """정의별 모형 성능과 라벨 품질을 시드에 걸쳐 평균·범위로 합친다."""
    names = [n for n in runs[0]["models"]]
    models = {n: {k: _stat([r["models"][n][k] for r in runs]) for k in runs[0]["models"][n]} for n in names}
    window = {
        n: {k: _stat([r["window"][n][k] for r in runs]) for k in runs[0]["window"][n]}
        for n in runs[0]["window"]
    }
    out = {"seeds": [r["seed"] for r in runs], "models": models, "window": window}
    d = [n for n in DEFS if n in models]
    best_own = [max(d, key=lambda n: r["models"][n]["own_auc"]) for r in runs]
    best_truth = [max(d, key=lambda n: r["models"][n]["truth_auc"]) for r in runs]
    out["best_by_own_auc"] = best_own
    out["best_by_truth_auc"] = best_truth
    out["auc_spread"] = _stat(
        [
            max(r["models"][n]["truth_auc"] for n in d) - min(r["models"][n]["truth_auc"] for n in d)
            for r in runs
        ]
    )
    out["d2_minus_d1_auc"] = _stat(
        [r["models"]["d2_corrective"]["truth_auc"] - r["models"]["d1_emergency"]["truth_auc"] for r in runs]
    )
    out["d2_beats_d1"] = int(
        sum(
            r["models"]["d2_corrective"]["truth_auc"] > r["models"]["d1_emergency"]["truth_auc"] for r in runs
        )
    )
    if "custom" in runs[0]:
        keys = runs[0]["custom"]["strategies"].keys()
        out["strategies"] = {
            k: {
                m: _stat([r["custom"]["strategies"][k][m] for r in runs])
                for m in ("truth_auc", "truth_ap", "truth_per100", "truth_site_auc")
            }
            for k in keys
        }
        out["audit"] = {
            "n_grid": runs[0]["audit"]["n_grid"],
            "p_near": [
                float(np.mean([r["audit"]["p_near"][i] for r in runs]))
                for i in range(len(runs[0]["audit"]["n_grid"]))
            ],
            "regret": [
                float(np.mean([r["audit"]["regret"][i] for r in runs]))
                for i in range(len(runs[0]["audit"]["n_grid"]))
            ],
        }
    return out


def build_summary(
    base: dict, multi: dict, drift: dict, validity: dict, audit: dict, robustness: dict | None = None
) -> dict:
    """README 와 콘솔이 쓰는 대표 숫자. 키는 scripts/fill_numbers.py 마커에서 `summary.<경로>` 로 쓴다."""
    b, u = multi["base"], multi["uniform"]
    lab = base["labels"]["definitions"]
    d1 = lab["d1_emergency"]
    arch = {a: d1["by_archetype"][a] for a in d1["by_archetype"]}
    sens = base["sensitivity"]
    names = sens["overlap"]["names"]
    ov = sens["overlap"]["matrix"]
    i1, i2 = names.index("d1_emergency"), names.index("d2_corrective")
    strat = b["strategies"]
    n90 = audit["n_for_90pct"]
    k80 = audit["n_grid"].index(80)
    rob = {}
    if robustness:
        for st, v in robustness["results"].items():
            rob[st.replace(".", "_")] = {
                "d1": v["d1_emergency"],
                "d2": v["d2_corrective"],
                "d3": v["d3_corroborated"],
                "truth": v["truth"],
                "d2_minus_d1": v["d2_corrective"] - v["d1_emergency"],
            }
    return {
        "robustness": rob,
        "worlds": {"base_seeds": len(b["seeds"]), "uniform_seeds": len(u["seeds"])},
        "auc": {
            "d1": b["models"]["d1_emergency"]["truth_auc"]["mean"],
            "d2": b["models"]["d2_corrective"]["truth_auc"]["mean"],
            "d3": b["models"]["d3_corroborated"]["truth_auc"]["mean"],
            "truth_label": b["models"]["truth"]["truth_auc"]["mean"],
            "oracle": b["models"]["oracle"]["truth_auc"]["mean"],
            "d2_minus_d1": b["d2_minus_d1_auc"]["mean"],
            "d2_minus_d1_min": b["d2_minus_d1_auc"]["min"],
            "d2_beats_d1_seeds": b["d2_beats_d1"],
            "spread": b["auc_spread"]["mean"],
            "spread_uniform": u["auc_spread"]["mean"],
            "d1_uniform": u["models"]["d1_emergency"]["truth_auc"]["mean"],
            "d2_uniform": u["models"]["d2_corrective"]["truth_auc"]["mean"],
        },
        "apparent": {
            "d1_own_auc": b["models"]["d1_emergency"]["own_auc"]["mean"],
            "d2_own_auc": b["models"]["d2_corrective"]["own_auc"]["mean"],
            "d1_truth_auc": b["models"]["d1_emergency"]["truth_auc"]["mean"],
            "d2_truth_auc": b["models"]["d2_corrective"]["truth_auc"]["mean"],
            "best_by_own_is_best_by_truth": int(
                sum(a == t for a, t in zip(b["best_by_own_auc"], b["best_by_truth_auc"], strict=True))
            ),
        },
        "labels": {
            "d1_recall": d1["overall"]["recall"],
            "d1_precision": d1["overall"]["precision"],
            "d1_recall_no_emergency_sites": arch["긴급 안 씀"]["recall"],
            "d1_recall_standard_sites": arch["표준"]["recall"],
            "d1_precision_abuse_sites": arch["긴급 남용"]["precision"],
            "d3_recall": lab["d3_corroborated"]["overall"]["recall"],
            "d3_precision": lab["d3_corroborated"]["overall"]["precision"],
            "d2_recall": lab["d2_corrective"]["overall"]["recall"],
            "d2_precision": lab["d2_corrective"]["overall"]["precision"],
        },
        "overlap": {"d1_d2": ov[i1][i2], "d1_truth": ov[i1][-1], "d2_truth": ov[i2][-1]},
        "validity": {m: v for m, v in validity["mean"].items()},
        "audit": {
            "n_for_90pct": n90,
            "p_near_80": audit["p_near"][k80],
            "regret_80": audit["regret"][k80],
            "p_near_40": audit["p_near"][audit["n_grid"].index(40)],
            "regret_10": audit["regret"][0],
        },
        "customization": {
            "fixed_d1": strat["fixed_d1_emergency"]["truth_auc"]["mean"],
            "fixed_d2": strat["fixed_d2_corrective"]["truth_auc"]["mean"],
            "fixed_d3": strat["fixed_d3_corroborated"]["truth_auc"]["mean"],
            "audit_40": strat["audit_40"]["truth_auc"]["mean"],
            "audit_80": strat["audit_80"]["truth_auc"]["mean"],
            "oracle": strat["oracle"]["truth_auc"]["mean"],
            "truth": strat["truth"]["truth_auc"]["mean"],
        },
        "maturity": {
            "mature_minus_current": base["maturity"]["training_variants"]["충분히 기다린 라벨로 학습"][
                "truth_auc"
            ]
            - base["maturity"]["training_variants"]["지금까지 입력된 기록으로 학습"]["truth_auc"],
        },
        "drift": {
            "shifts": drift["shifts_total"],
            "detected": drift["shifts_detected"],
            "delay_median_weeks": drift["delay_median_weeks"],
            "delay_max_weeks": drift["delay_max_weeks"],
            "false_alarm_site_runs": drift["false_alarm_site_runs"],
            "quiet_site_runs": drift["quiet_site_runs"],
            "d1_f1_before": float(
                np.mean(
                    [r["label_quality_shifted_sites"]["d1_emergency"]["before"]["f1"] for r in drift["runs"]]
                )
            ),
            "d1_f1_after": float(
                np.mean(
                    [r["label_quality_shifted_sites"]["d1_emergency"]["after"]["f1"] for r in drift["runs"]]
                )
            ),
        },
    }
