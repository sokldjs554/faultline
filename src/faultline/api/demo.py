"""데모 세계. 정의 평가 API 와 샘플 CSV 가 같은 세계(시드 7)를 쓴다. 처음 부를 때 한 번 만든다."""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from faultline.define.spec import Definition, builtin
from faultline.eval import experiments as E
from faultline.eval import protocol as P
from faultline.eval.labels import match_incidents, public
from faultline.sim.world import WorldConfig, simulate

SAMPLE_SITES = (0, 1, 5)  # 표준, 긴급 안 씀, 코드 다름(코드표가 없으면 유형을 못 읽는다)


@lru_cache(maxsize=1)
def prepared() -> P.Prepared:
    return P.prepare(simulate(WorldConfig(seed=7)))


def evaluate_definition(defn: Definition, train: bool = False) -> dict:
    """정의를 데모 세계에 적용해 라벨 품질을 정답과 맞춰 본다. train 이면 그 라벨로 모형을 학습해 진짜 성능도 잰다."""
    prep = prepared()
    w = prep.world
    res = P.incidents_for(prep, defn)
    inc = res.incidents
    arch = w.sites.set_index("site")["archetype"]
    by_arch = {}
    for a in arch.unique():
        sites = arch[arch == a].index
        by_arch[a] = public(match_incidents(inc[inc["site"].isin(sites)], w.failures[w.failures["site"].isin(sites)]))
    out = {
        "definition": defn.to_dict(),
        "incidents": int(len(inc)),
        "evidence": inc["evidence"].value_counts().to_dict() if len(inc) else {},
        "overall": public(match_incidents(inc, w.failures)),
        "by_archetype": by_arch,
        "window": E.window_quality(prep, {defn.name: defn})[defn.name],
        "stats": res.stats,
    }
    if train:
        y = P.labels_for(prep, defn, E.AS_OF)
        r, _ = E._metrics(prep, E._score(prep, y), P.labels_for(prep, defn, None))
        out["model"] = {k: r[k] for k in ("truth_auc", "truth_ap", "truth_per100", "own_auc")}
        ref = {n: E._metrics(prep, E._score(prep, P.labels_for(prep, d, E.AS_OF)), None)[0]["truth_auc"] for n, d in builtin().items() if n in ("d1_emergency", "d2_corrective")}
        out["model"]["reference_truth_auc"] = ref
    return out


def sample_tables() -> dict:
    """샘플 업로드용 표. 사이트 몇 곳의 작업지시, 민원, 설비."""
    w = prepared().world
    sites = list(SAMPLE_SITES)
    assets = w.assets[w.assets["site"].isin(sites)]
    wo = w.wo[w.wo["site"].isin(sites)][["wo_id", "site", "asset", "created_day", "closed_day", "type_raw"]]
    cm = w.complaints[w.complaints["site"].isin(sites)]
    return {"work_orders": wo, "complaints": cm, "assets": assets, "weeks": w.cfg.weeks, "n_sites": len(np.unique(sites))}
