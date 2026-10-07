"""기록만으로 만드는 설비·주 단위 특징.

t 주를 마친 시점에 입력되어 있던 기록만 쓴다. 정의와 무관하게 같은 특징을 모든 정의의 모형이 공유한다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from faultline.define.engine import SYM_CODE, _compat
from faultline.sim.world import CATS

CAT_CODE = {c.key: i for i, c in enumerate(CATS)}

NUMERIC = [
    "age_years",
    "central",
    "weeks_since_pm",
    "last_pm_grade",
    "wo_np_4",
    "wo_np_12",
    "wo_np_26",
    "wo_em_12",
    "wo_em_26",
    "cmp_4",
    "cmp_12",
    "weeks_since_wo",
    "site_np_rate_26",
    "site_em_share_26",
    "week_sin",
    "week_cos",
]
FEATURES = ["category", *NUMERIC]


@dataclass
class FeatureSet:
    X: pd.DataFrame  # 행 = 설비 x 주(주 t_min 부터), 열 = FEATURES
    asset_idx: np.ndarray
    week: np.ndarray
    site: np.ndarray
    n_assets: int
    n_weeks: int


def _weekly(asset_pos: np.ndarray, day: np.ndarray, n_assets: int, n_weeks: int) -> np.ndarray:
    m = np.zeros((n_assets, n_weeks), dtype=np.float32)
    wk = np.clip(day // 7, 0, n_weeks - 1).astype(int)
    np.add.at(m, (asset_pos, wk), 1.0)
    return m


def _roll(cum: np.ndarray, k: int) -> np.ndarray:
    """cum 은 앞에 0 열이 붙은 누적합. t 주까지 최근 k 주 합을 (설비 x 주) 로 돌려준다."""
    n_weeks = cum.shape[1] - 1
    t = np.arange(n_weeks)
    return cum[:, t + 1] - cum[:, np.maximum(0, t + 1 - k)]


def build_features(
    assets: pd.DataFrame,
    wo_norm: pd.DataFrame,
    complaints: pd.DataFrame,
    pm: pd.DataFrame,
    n_weeks: int,
    t_min: int = 26,
) -> FeatureSet:
    A = len(assets)
    apos = pd.Series(np.arange(A), index=assets["asset"].to_numpy())
    wo = wo_norm[wo_norm["asset"].notna()].drop_duplicates(
        subset=["wo_id", "asset", "created_day", "type_raw"]
    )
    ai = apos.reindex(wo["asset"].astype(int).to_numpy()).to_numpy()
    wo = wo[~np.isnan(ai)]
    ai = ai[~np.isnan(ai)].astype(int)
    np_mask = (wo["wo_kind"] != "preventive").to_numpy()
    em_mask = (wo["wo_kind"] == "emergency").to_numpy()
    days = wo["created_day"].to_numpy()
    np_w = _weekly(ai[np_mask], days[np_mask], A, n_weeks)
    em_w = _weekly(ai[em_mask], days[em_mask], A, n_weeks)

    # 민원은 증상, 층, 설비 단서가 맞는 설비 모두에게 센다
    cmp_w = np.zeros((A, n_weeks), dtype=np.float32)
    a_cat = assets["category"].to_numpy()
    a_floor = assets["floor"].to_numpy()
    a_site = assets["site"].to_numpy()
    a_id = assets["asset"].to_numpy()
    ok = _compat(a_cat)
    site_idx = {s: np.flatnonzero(a_site == s) for s in np.unique(a_site)}
    for s, g in complaints.groupby("site"):
        idx = site_idx[s]
        for day, floor, sym, hint in zip(g["day"], g["floor"], g["symptom"], g["hint_asset"], strict=True):
            m = ok[idx, SYM_CODE[sym]] & ((a_floor[idx] == -1) | (a_floor[idx] == floor))
            if not np.isnan(hint):
                m &= a_id[idx] == int(hint)
            cmp_w[idx[m], min(max(int(day) // 7, 0), n_weeks - 1)] += 1.0

    cum = lambda m: np.concatenate([np.zeros((A, 1), dtype=np.float32), np.cumsum(m, axis=1)], axis=1)  # noqa: E731
    c_np, c_em, c_cmp = cum(np_w), cum(em_w), cum(cmp_w)

    pm_ai = apos.reindex(pm["asset"].to_numpy()).to_numpy().astype(int)
    pm_week = np.clip(pm["day"].to_numpy() // 7, 0, n_weeks - 1).astype(int)
    pm_grade = np.full((A, n_weeks), np.nan, dtype=np.float32)
    pm_grade[pm_ai, pm_week] = pm["grade"].to_numpy()

    since_pm = np.zeros((A, n_weeks), dtype=np.float32)
    last_grade = np.full((A, n_weeks), -1.0, dtype=np.float32)
    since_wo = np.zeros((A, n_weeks), dtype=np.float32)
    sp = np.full(A, 52.0, dtype=np.float32)
    lg = np.full(A, -1.0, dtype=np.float32)
    sw = np.full(A, 52.0, dtype=np.float32)
    for t in range(n_weeks):
        sp += 1
        sw += 1
        hit = ~np.isnan(pm_grade[:, t])
        sp[hit] = 0
        lg[hit] = pm_grade[hit, t]
        sw[np_w[:, t] > 0] = 0
        since_pm[:, t], last_grade[:, t], since_wo[:, t] = np.minimum(sp, 52), lg, np.minimum(sw, 52)

    # 사이트 수준 기록 습관: 최근 26주 시정 작업지시 비율과 긴급 비중
    site_np = np.zeros((A, n_weeks), dtype=np.float32)
    site_em = np.zeros((A, n_weeks), dtype=np.float32)
    np26, em26 = _roll(c_np, 26), _roll(c_em, 26)
    for idx in site_idx.values():
        tot_np, tot_em = np26[idx].sum(0), em26[idx].sum(0)
        site_np[idx] = (tot_np / len(idx))[None, :]
        site_em[idx] = (tot_em / np.maximum(tot_np, 1.0))[None, :]

    t = np.arange(n_weeks)
    age = assets["age_years"].to_numpy()[:, None] + t[None, :] / 52.0
    cat_code = assets["category"].map(CAT_CODE).to_numpy()[:, None] * np.ones((1, n_weeks))
    central = (a_floor == -1).astype(np.float32)[:, None] * np.ones((1, n_weeks), dtype=np.float32)
    ph = 2 * np.pi * (t % 52) / 52.0

    cols = {
        "category": cat_code,
        "age_years": age,
        "central": central,
        "weeks_since_pm": since_pm,
        "last_pm_grade": last_grade,
        "wo_np_4": _roll(c_np, 4),
        "wo_np_12": _roll(c_np, 12),
        "wo_np_26": np26,
        "wo_em_12": _roll(c_em, 12),
        "wo_em_26": em26,
        "cmp_4": _roll(c_cmp, 4),
        "cmp_12": _roll(c_cmp, 12),
        "weeks_since_wo": since_wo,
        "site_np_rate_26": site_np,
        "site_em_share_26": site_em,
        "week_sin": np.sin(ph)[None, :] * np.ones((A, 1)),
        "week_cos": np.cos(ph)[None, :] * np.ones((A, 1)),
    }
    sel = np.arange(t_min, n_weeks)
    ai_grid, wk_grid = np.meshgrid(np.arange(A), sel, indexing="ij")
    X = pd.DataFrame({k: v[:, sel].ravel() for k, v in cols.items()})[FEATURES]
    X["category"] = X["category"].astype(int)
    return FeatureSet(X, ai_grid.ravel(), wk_grid.ravel(), a_site[ai_grid.ravel()], A, n_weeks)
