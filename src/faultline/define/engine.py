"""고장 정의를 로그에 적용해 사건(incident) 표를 만든다.

증거: 작업지시(유형이 정규화된 것)와 민원. 정의 파일이 어떤 증거를 고장으로 칠지, 같은 건을 어떻게 묶을지, 사건 시각을 어떻게 잡을지 정한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from faultline.define.spec import Definition
from faultline.sim.world import CAT_BY_KEY, SYMPTOM_CATS

SYMPTOMS = sorted({s for c in CAT_BY_KEY.values() for s in c.symptoms})
SYM_CODE = {s: i for i, s in enumerate(SYMPTOMS)}


@dataclass
class DefinitionResult:
    incidents: pd.DataFrame
    stats: dict


def _compat(a_cat: np.ndarray) -> np.ndarray:
    ok = np.zeros((len(a_cat), len(SYMPTOMS)), dtype=bool)
    for i, cat in enumerate(a_cat):
        for s in CAT_BY_KEY[cat].symptoms:
            ok[i, SYM_CODE[s]] = True
    return ok


def _wo_events(defn: Definition, w: pd.DataFrame, c: pd.DataFrame, a: pd.DataFrame, stats: dict) -> list[tuple[int, int]]:
    cand = w[w["wo_kind"].isin(defn.wo_kinds)]
    stats["wo_missing_asset"] += int(cand["asset"].isna().sum())
    cand = cand[cand["asset"].notna()].drop_duplicates(subset=["wo_id", "asset", "created_day", "type_raw"])
    if cand.empty:
        return []
    a_id, a_cat, a_floor = a["asset"].to_numpy(), a["category"].to_numpy(), a["floor"].to_numpy()
    pos = {int(x): i for i, x in enumerate(a_id)}
    ca = cand["asset"].astype(int).to_numpy()
    known = np.array([x in pos for x in ca])
    cand, ca = cand[known], ca[known]
    if cand.empty:
        return []
    ai = np.array([pos[x] for x in ca])
    cd = cand["created_day"].to_numpy()
    em = (cand["wo_kind"] == "emergency").to_numpy()
    first = np.full(len(cand), np.inf)
    support = np.zeros(len(cand), dtype=int)
    if defn.wo_require != "none" and len(c):
        ok = _compat(a_cat)
        c_day = c["day"].to_numpy()
        c_floor = c["floor"].to_numpy()
        c_sym = c["symptom"].map(SYM_CODE).to_numpy()
        c_hint = c["hint_asset"].to_numpy(dtype=float)
        lo, hi = defn.support_window
        m = (c_day[None, :] >= cd[:, None] + lo) & (c_day[None, :] <= cd[:, None] + hi)
        m &= ok[ai][:, c_sym]
        m &= (a_floor[ai][:, None] == -1) | (a_floor[ai][:, None] == c_floor[None, :])
        m &= np.isnan(c_hint)[None, :] | (c_hint[None, :] == ca[:, None])
        support = m.sum(1)
        first = np.where(m, c_day[None, :], np.inf).min(1)
    if defn.wo_require == "none":
        keep = np.ones(len(cand), dtype=bool)
    elif defn.wo_require == "emergency_or_complaint":
        keep = em | (support > 0)
    else:
        keep = support > 0
    day = cd.astype(float)
    if defn.event_time == "earliest_evidence":
        day = np.minimum(day, first)
    return [(int(x), int(d)) for x, d in zip(ca[keep], day[keep], strict=True)]


def _cluster_events(defn: Definition, c: pd.DataFrame, a: pd.DataFrame, stats: dict) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    if c.empty:
        return out
    a_id, a_cat, a_floor = a["asset"].to_numpy(), a["category"].to_numpy(), a["floor"].to_numpy()
    for sym, g in c.groupby("symptom"):
        g = g.sort_values("day")
        days = g["day"].to_numpy()
        floors = g["floor"].to_numpy()
        hints = g["hint_asset"].to_numpy(dtype=float)
        cuts = np.flatnonzero(np.diff(days) > defn.cluster_window_days) + 1
        for idx in np.split(np.arange(len(g)), cuts):
            if len(idx) < defn.cluster_min_count:
                continue
            hs = hints[idx]
            hs = hs[~np.isnan(hs)]
            if len(hs):
                u = np.unique(hs)
                if len(u) == 1 and int(u[0]) in set(a_id.tolist()):
                    out.append((int(u[0]), int(days[idx[0]])))
                else:
                    stats["unresolved_clusters"] += 1
                continue
            mask = np.isin(a_cat, SYMPTOM_CATS[sym])
            vals, counts = np.unique(floors[idx], return_counts=True)
            if counts.max() / len(idx) >= 0.6:
                mask &= (a_floor == vals[counts.argmax()]) | (a_floor == -1)
            else:
                mask &= a_floor == -1
            cand = a_id[mask]
            if len(cand) == 1:
                out.append((int(cand[0]), int(days[idx[0]])))
            else:
                stats["unresolved_clusters"] += 1
    return out


def apply_definition(
    defn: Definition,
    wo_norm: pd.DataFrame,
    complaints: pd.DataFrame,
    assets: pd.DataFrame,
    as_of_day: int | None = None,
) -> DefinitionResult:
    """정의를 적용한다. `as_of_day` 를 주면 그날까지 입력된 기록만 쓴다(그 시점의 라벨을 재현할 때)."""
    if as_of_day is not None:
        wo_norm = wo_norm[wo_norm["created_day"] <= as_of_day]
        complaints = complaints[complaints["day"] <= as_of_day]
    stats = {"wo_missing_asset": 0, "unresolved_clusters": 0}
    rows: list[tuple[int, int, int, int]] = []  # site, asset, day, source
    wo_by = {k: v for k, v in wo_norm.groupby("site")}
    c_by = {k: v for k, v in complaints.groupby("site")}
    for site, a in assets.groupby("site"):
        w = wo_by.get(site)
        c = c_by.get(site, complaints.iloc[0:0])
        if w is not None:
            rows += [(int(site), x, d, 0) for x, d in _wo_events(defn, w, c, a, stats)]
        if defn.cluster_enabled:
            rows += [(int(site), x, d, 1) for x, d in _cluster_events(defn, c, a, stats)]
    ev = pd.DataFrame(rows, columns=["site", "asset", "day", "src"])
    if ev.empty:
        return DefinitionResult(pd.DataFrame(columns=["incident_id", "site", "asset", "day", "n_records", "evidence"]), stats)
    ev = ev.sort_values(["asset", "day"], kind="stable").reset_index(drop=True)
    gap = ev.groupby("asset")["day"].diff()
    inc = ((gap.isna()) | (gap > defn.merge_window_days)).cumsum()
    g = ev.groupby(inc)
    out = pd.DataFrame(
        {
            "site": g["site"].first(),
            "asset": g["asset"].first(),
            "day": g["day"].min(),
            "n_records": g.size(),
            "has_wo": g["src"].min() == 0,
            "has_cmp": g["src"].max() == 1,
        }
    ).reset_index(drop=True)
    out["evidence"] = np.where(out["has_wo"] & out["has_cmp"], "wo+complaint", np.where(out["has_cmp"], "complaint", "wo"))
    out = out.drop(columns=["has_wo", "has_cmp"]).sort_values(["day", "asset"], kind="stable").reset_index(drop=True)
    out.insert(0, "incident_id", np.arange(len(out)))
    return DefinitionResult(out, stats)
