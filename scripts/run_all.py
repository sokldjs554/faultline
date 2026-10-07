"""실험 전체를 돌려 artifacts/ 에 JSON 으로 쓴다.

    python scripts/run_all.py --stage all
단계: base(시드 7 한 세계의 상세), quality(데이터 품질 점검), audit_demo(현장 확인 시뮬레이션), uniform(대조 세계), seeds(여러 시드), drift(습관 변화 감시), robustness(전조 신호 가정), summary, manifest.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np

from faultline.define import spec
from faultline.eval import experiments as E
from faultline.eval import protocol as P
from faultline.eval import summary as S
from faultline.sim.world import WorldConfig, simulate

BASE_SEEDS = (7, 11, 23, 31, 47)
UNIFORM_SEEDS = (7, 11, 23)
OUT = Path("artifacts")


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return _jsonable(o.tolist())
    return o


def write(name: str, data) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(_jsonable(data), ensure_ascii=False, separators=(",", ":")))
    print(f"  {name}.json")


def read(name: str):
    return json.loads((OUT / f"{name}.json").read_text())


def topk_view(
    prep: P.Prepared, defs: dict, names=("d1_emergency", "d2_corrective", "d3_corroborated")
) -> dict:
    """같은 점검 인력(사이트·주마다 상위 5개)을 정의별 모형이 어떻게 쓰는가. 사이트 습관별 적중 수와 예시 한 주."""
    w = prep.world
    te = prep.test_rows
    arch = w.sites.set_index("site")["archetype"]
    site = prep.fs.site[te]
    week = prep.fs.week[te]
    yt = P.rows_of(prep, prep.y_truth, te)
    scores = {n: E._score(prep, P.labels_for(prep, defs[n], E.AS_OF)) for n in names}
    scores["truth"] = E._score(prep, prep.y_truth)
    sel = {n: P.topk_flags(s, site, week) for n, s in scores.items()}
    per = {}
    for a in arch.unique():
        m = np.isin(site, arch[arch == a].index)
        per[a] = {n: float(100 * yt[sel[n] & m].sum() / max((sel[n] & m).sum(), 1)) for n in sel}
        per[a]["random"] = float(100 * yt[m].mean())
    # 예시 한 주: 습관 유형마다 d1 과 d2 의 선택이 가장 다르면서 정답 고장이 있는 주
    ex = []
    assets = w.assets.set_index("asset")
    for a in ("긴급 안 씀", "긴급 남용", "표준"):
        s0 = int(arch[arch == a].index[0])
        best = None
        for wk in np.unique(week):
            m = (site == s0) & (week == wk)
            if not m.any():
                continue
            j = P.jaccard(sel["d1_emergency"] & m, sel["d2_corrective"] & m)
            hits = int(yt[m & (sel["d1_emergency"] | sel["d2_corrective"])].sum())
            if hits >= 1 and (best is None or j < best[0]):
                best = (j, int(wk))
        if best is None:
            continue
        wk = best[1]
        m = (site == s0) & (week == wk)
        lists = {}
        for n in sel:
            idx = np.flatnonzero(m & sel[n])
            idx = idx[np.argsort(-scores[n][idx])]
            lists[n] = [
                {
                    "asset": int(assets.index[int(prep.fs.asset_idx[te][i])]),
                    "category": str(assets.iloc[int(prep.fs.asset_idx[te][i])]["category"]),
                    "floor": int(assets.iloc[int(prep.fs.asset_idx[te][i])]["floor"]),
                    "failed_in_4w": bool(yt[i]),
                }
                for i in idx
            ]
        ex.append({"site": s0, "archetype": a, "week": int(wk), "lists": lists})
    return {"per100_by_archetype": per, "examples": ex, "topk": P.TOPK}


def timeline_view(prep: P.Prepared, defs: dict) -> dict:
    """사이트 한 곳의 정답 고장과 정의별 사건. 같은 로그에서 정의마다 다른 사건이 나온다."""
    w = prep.world
    arch = w.sites.set_index("site")["archetype"]
    out = {"sites": {}}
    for a in ("표준", "긴급 안 씀", "긴급 남용", "입력 누락", "늦게 입력", "코드 다름"):
        s0 = int(arch[arch == a].index[0])
        f = w.failures[w.failures["site"] == s0]
        item = {
            "site": s0,
            "archetype": a,
            "n_assets": int((w.assets["site"] == s0).sum()),
            "failures": [{"asset": int(r.asset), "day": int(r.day)} for r in f.itertuples()],
            "definitions": {},
        }
        for name, d in defs.items():
            inc = P.incidents_for(prep, d).incidents
            g = inc[inc["site"] == s0]
            item["definitions"][name] = [
                {"asset": int(r.asset), "day": int(r.day), "evidence": r.evidence} for r in g.itertuples()
            ]
        out["sites"][a] = item
    out["weeks"] = w.cfg.weeks
    return out


def stage_base() -> None:
    print("base (seed 7)")
    defs = spec.builtin()
    world = simulate(WorldConfig(seed=7))
    prep = P.prepare(world)
    labels = E.exp_labels(prep, defs)
    sens = E.exp_sensitivity(prep, defs)
    audit = E.exp_audit(prep, defs, reps=300)
    custom = E.exp_custom(prep, defs, audit)
    maturity = E.exp_maturity(prep, defs)
    write(
        "base",
        {
            "world": {
                "seed": 7,
                "sites": len(world.sites),
                "assets": len(world.assets),
                "weeks": world.cfg.weeks,
                "work_orders": len(world.wo),
                "complaints": len(world.complaints),
                "failures": len(world.failures),
                "failures_per_asset_year": len(world.failures) / (len(world.assets) * world.cfg.weeks / 52.0),
                "site_table": world.sites.to_dict(orient="records"),
            },
            "labels": labels,
            "sensitivity": sens,
            "audit": audit,
            "custom": custom,
            "maturity": maturity,
            "topk": topk_view(prep, defs),
            "timeline": timeline_view(prep, defs),
        },
    )


def stage_quality() -> None:
    print("quality (seed 7)")
    prep = P.prepare(simulate(WorldConfig(seed=7)))
    write("quality", E.exp_quality(prep, spec.builtin()))


def stage_audit_demo() -> None:
    print("audit_demo (seed 7)")
    defs = spec.builtin()
    prep = P.prepare(simulate(WorldConfig(seed=7)))
    write("audit_demo", E.exp_audit_demo(prep, defs))


def stage_uniform() -> None:
    print("uniform (seed 7)")
    defs = spec.builtin()
    world = simulate(WorldConfig(seed=7, uniform_habit=True))
    prep = P.prepare(world)
    write(
        "uniform", {"labels": E.exp_labels(prep, defs), "sensitivity": E.exp_sensitivity(prep, defs, mlp=())}
    )


def stage_seeds() -> None:
    print("seeds")
    base_runs = []
    for s in BASE_SEEDS:
        print("  base", s, flush=True)
        base_runs.append(E.exp_seed(s))
    uni_runs = []
    for s in UNIFORM_SEEDS:
        print("  uniform", s, flush=True)
        uni_runs.append(E.exp_seed(s, uniform=True))
    write(
        "multiseed",
        {
            "base": S.aggregate_runs(base_runs),
            "uniform": S.aggregate_runs(uni_runs),
            "runs": {"base": base_runs, "uniform": uni_runs},
        },
    )
    write("validity", E.exp_metric_validity(base_runs))


def stage_drift() -> None:
    print("drift")
    write("drift", E.exp_drift(BASE_SEEDS))


def stage_robustness() -> None:
    print("robustness")
    write("robustness", E.exp_robustness())


def stage_summary() -> None:
    print("summary")
    base, multi, drift, validity, rob = (
        read("base"),
        read("multiseed"),
        read("drift"),
        read("validity"),
        read("robustness"),
    )
    write("summary", S.build_summary(base, multi, drift, validity, rob))


def stage_manifest() -> None:
    import fastapi
    import pandas
    import sklearn
    import torch

    cfg = WorldConfig()
    write(
        "manifest",
        {
            "base_seeds": list(BASE_SEEDS),
            "uniform_seeds": list(UNIFORM_SEEDS),
            "world_config": {
                k: getattr(cfg, k)
                for k in (
                    "n_sites",
                    "weeks",
                    "burn_in",
                    "horizon_days",
                    "target_failures_per_asset_year",
                    "beta",
                    "minor_gain",
                    "pre_cmp_rate",
                    "p_stop",
                )
            },
            "protocol": {
                "horizon_weeks": P.HORIZON,
                "train_weeks": [P.T_MIN, P.TRAIN_END],
                "cutoff_week": P.CUTOFF_WEEK,
                "test_start_week": P.TEST_START,
                "topk": P.TOPK,
                "audit_beta": E.AUDIT_BETA,
            },
            "definitions": {n: d.to_dict() for n, d in spec.builtin().items()},
            "versions": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "pandas": pandas.__version__,
                "scikit-learn": sklearn.__version__,
                "torch": torch.__version__,
                "fastapi": fastapi.__version__,
            },
        },
    )


STAGES = {
    "base": stage_base,
    "quality": stage_quality,
    "audit_demo": stage_audit_demo,
    "uniform": stage_uniform,
    "seeds": stage_seeds,
    "drift": stage_drift,
    "robustness": stage_robustness,
    "summary": stage_summary,
    "manifest": stage_manifest,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=["all", *STAGES])
    ap.add_argument("--out", type=Path, default=Path("artifacts"))
    a = ap.parse_args()
    global OUT
    OUT = a.out
    for name, fn in STAGES.items():
        if a.stage in ("all", name):
            fn()
    return 0


if __name__ == "__main__":
    sys.exit(main())
