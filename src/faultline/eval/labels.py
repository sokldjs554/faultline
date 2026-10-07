"""라벨 품질: 정의가 만든 사건을 진짜 고장과 맞춰 본다."""

from __future__ import annotations

import numpy as np
import pandas as pd


def match_incidents(incidents: pd.DataFrame, failures: pd.DataFrame, tol_days: int = 14) -> dict:
    """같은 설비에서 날짜 차이가 tol_days 이내인 사건과 진짜 고장을 1대1로 짝짓는다(가까운 쌍부터)."""
    inc_by = {k: g["day"].to_numpy() for k, g in incidents.groupby("asset")}
    f_by = {k: g["day"].to_numpy() for k, g in failures.groupby("asset")}
    tp, errs = 0, []
    inc_matched = np.zeros(len(incidents), dtype=bool)
    fail_matched = np.zeros(len(failures), dtype=bool)
    inc_idx = {k: np.flatnonzero((incidents["asset"] == k).to_numpy()) for k in inc_by}
    fail_idx = {k: np.flatnonzero((failures["asset"] == k).to_numpy()) for k in f_by}
    for asset, idays in inc_by.items():
        fdays = f_by.get(asset)
        if fdays is None:
            continue
        pairs = [
            (abs(int(i) - int(f)), a, b)
            for a, i in enumerate(idays)
            for b, f in enumerate(fdays)
            if abs(int(i) - int(f)) <= tol_days
        ]
        pairs.sort()
        used_i, used_f = set(), set()
        for _d, a, b in pairs:
            if a in used_i or b in used_f:
                continue
            used_i.add(a)
            used_f.add(b)
            tp += 1
            errs.append(int(idays[a]) - int(fdays[b]))
            inc_matched[inc_idx[asset][a]] = True
            fail_matched[fail_idx[asset][b]] = True
    n_inc, n_fail = len(incidents), len(failures)
    precision = tp / n_inc if n_inc else float("nan")
    recall = tp / n_fail if n_fail else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if tp else 0.0
    return {
        "incidents": int(n_inc),
        "failures": int(n_fail),
        "matched": int(tp),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "timing_median": float(np.median(errs)) if errs else float("nan"),
        "timing_p90": float(np.percentile(np.abs(errs), 90)) if errs else float("nan"),
        "inc_matched": inc_matched,
        "fail_matched": fail_matched,
    }


def public(m: dict) -> dict:
    return {k: v for k, v in m.items() if not isinstance(v, np.ndarray)}


def event_week_matrix(events: pd.DataFrame, assets: pd.DataFrame, n_weeks: int) -> np.ndarray:
    """설비 x 주 사건 개수 행렬. 설비 순서는 assets 표를 따른다."""
    pos = pd.Series(np.arange(len(assets)), index=assets["asset"].to_numpy())
    m = np.zeros((len(assets), n_weeks), dtype=np.int32)
    if events.empty:
        return m
    wk = (events["day"].to_numpy() // 7).astype(int)
    ai = pos.reindex(events["asset"].to_numpy()).to_numpy()
    ok = (wk >= 0) & (wk < n_weeks) & ~np.isnan(ai)
    np.add.at(m, (ai[ok].astype(int), wk[ok]), 1)
    return m


def window_labels(
    events: pd.DataFrame, assets: pd.DataFrame, n_weeks: int, horizon_weeks: int = 4
) -> np.ndarray:
    """설비 x 주 라벨 행렬. t 주를 마친 시점에서 다음 horizon_weeks 주 안에 사건이 있으면 1. 마지막 주들은 끝까지 관측되지 않아 NaN."""
    m = event_week_matrix(events, assets, n_weeks)
    cum = np.concatenate(
        [np.zeros((m.shape[0], 1), dtype=np.int32), np.cumsum(m, axis=1)], axis=1
    )  # cum[:, k] = 0..k-1 주 합
    y = np.full(m.shape, np.nan)
    for t in range(n_weeks - horizon_weeks):
        y[:, t] = (cum[:, t + 1 + horizon_weeks] - cum[:, t + 1]) > 0
    return y
