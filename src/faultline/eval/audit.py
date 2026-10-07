"""현장 확인: 확인할 설비·주를 뽑고, 확인 결과로 정의별 정밀도와 재현율을 추정한다.

설비·주 창마다 4주 안에 진짜 고장이 있었는지를 현장에서 확인한다. 정의가 만든 라벨만 보면 정의가 놓친 고장을 셀 수 없어서,
어느 정의든 고장으로 표시한 창(S1)과 아무도 표시하지 않은 창(S0)에서 따로 뽑고 층의 크기로 가중해 추정한다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from faultline.define.engine import apply_definition
from faultline.define.spec import Definition
from faultline.eval.labels import window_labels

AUDIT_BETA = 2.0  # 정의를 고를 때 재현율을 정밀도보다 두 배 무겁게 본다(근거는 docs/evaluation.md)
HORIZON_WEEKS = 4


def fbeta(tp: float, pred: float, pos: float, beta: float = 1.0) -> float:
    if tp <= 0 or pred <= 0 or pos <= 0:
        return 0.0
    p, r = tp / pred, tp / pos
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r)


def fbeta_vec(prec: np.ndarray, rec: np.ndarray, beta: float) -> np.ndarray:
    b2 = beta * beta
    den = b2 * prec + rec
    return np.where(den > 0, (1 + b2) * prec * rec / np.where(den > 0, den, 1.0), 0.0)


def audit_stats(
    L: np.ndarray, truth_sample: np.ndarray, idx_s1: np.ndarray, idx_s0: np.ndarray, n1_pop: int, n0_pop: int
) -> tuple[np.ndarray, np.ndarray]:
    """층화 표본에서 정의별 정밀도와 재현율을 추정한다(Horvitz-Thompson).

    truth_sample 은 S1 표본 다음에 S0 표본을 이어 붙인 확인 결과다.
    정의가 표시한 창은 모두 S1 안에 있으므로 맞힌 수(TP)는 S1 표본에서, 전체 고장 창 수는 두 층의 표본에서 추정한다.
    """
    k1 = len(idx_s1)
    w1 = n1_pop / max(k1, 1)
    w0 = n0_pop / max(len(idx_s0), 1)
    t_hat = w1 * truth_sample[:k1].sum() + w0 * truth_sample[k1:].sum()
    prec = np.zeros(L.shape[0])
    rec = np.zeros(L.shape[0])
    for k in range(L.shape[0]):
        pred = L[k].sum()
        tp = w1 * truth_sample[:k1][L[k][idx_s1]].sum()
        prec[k] = tp / pred if pred > 0 else 0.0
        rec[k] = min(tp / t_hat, 1.0) if t_hat > 0 else 0.0
    return prec, rec


def audit_estimate(
    L: np.ndarray,
    truth_sample: np.ndarray,
    idx_s1: np.ndarray,
    idx_s0: np.ndarray,
    n1_pop: int,
    n0_pop: int,
    beta: float = AUDIT_BETA,
) -> np.ndarray:
    """층화 표본에서 정의별 F-beta 를 추정한다."""
    prec, rec = audit_stats(L, truth_sample, idx_s1, idx_s0, n1_pop, n0_pop)
    return fbeta_vec(prec, rec, beta)


def draw_audit(
    L: np.ndarray, n: int, rng: np.random.Generator, share_s1: float = 0.5
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """확인할 창을 뽑는다. 절반은 어느 정의든 고장으로 표시한 창에서, 나머지는 아무도 표시하지 않은 창에서."""
    flagged = L.any(0)
    s1, s0 = np.flatnonzero(flagged), np.flatnonzero(~flagged)
    n1 = min(max(int(round(n * share_s1)), 1), len(s1))
    n0 = min(max(n - n1, 1), len(s0))
    a1 = rng.choice(s1, n1, replace=False) if len(s1) else np.array([], dtype=int)
    a0 = rng.choice(s0, n0, replace=False)
    return a1.astype(int), a0.astype(int), len(s1), len(s0)


def bootstrap_interval(
    L: np.ndarray,
    truth1: np.ndarray,
    truth0: np.ndarray,
    a1: np.ndarray,
    a0: np.ndarray,
    n1_pop: int,
    n0_pop: int,
    beta: float,
    rng: np.random.Generator,
    boot: int = 200,
) -> tuple[np.ndarray, np.ndarray]:
    """층 안에서 표본을 다시 뽑아 점수의 90% 구간을 구한다."""
    out = np.zeros((boot, L.shape[0]))
    for b in range(boot):
        i1 = rng.integers(0, len(a1), len(a1)) if len(a1) else np.array([], dtype=int)
        i0 = rng.integers(0, len(a0), len(a0))
        t = np.concatenate([truth1[i1], truth0[i0]]) if len(a1) else truth0[i0]
        out[b] = fbeta_vec(*audit_stats(L, t, a1[i1], a0[i0], n1_pop, n0_pop), beta)
    return np.percentile(out, 5, axis=0), np.percentile(out, 95, axis=0)


# ---------------------------------------------------------------- 실제 로그용
def site_windows(
    defs: dict[str, Definition],
    wo_norm: pd.DataFrame,
    complaints: pd.DataFrame,
    assets: pd.DataFrame,
    site,
    n_weeks: int,
) -> tuple[np.ndarray, pd.DataFrame]:
    """사이트 하나의 설비·주 창과 정의별 라벨. 4주가 다 관측된 주만 쓴다.

    돌려주는 L 은 (정의 수, 창 수) 불리언 행렬이고, 두 번째 값은 창마다 설비와 주를 적은 표다.
    """
    a = assets[assets["site"] == site].reset_index(drop=True)
    w = wo_norm[wo_norm["site"] == site]
    c = complaints[complaints["site"] == site]
    n_win = n_weeks - HORIZON_WEEKS
    if n_win < 1 or a.empty:
        raise ValueError("관측 기간이 4주보다 짧거나 사이트에 설비가 없다")
    rows = []
    for d in defs.values():
        inc = apply_definition(d, w, c, a).incidents
        y = window_labels(inc, a, n_weeks, HORIZON_WEEKS)[:, :n_win]
        rows.append((y == 1).ravel())
    index = pd.DataFrame(
        {"asset": np.repeat(a["asset"].to_numpy(), n_win), "week": np.tile(np.arange(n_win), len(a))}
    )
    return np.array(rows, dtype=bool), index


def plan_sample(
    defs: dict[str, Definition], L: np.ndarray, index: pd.DataFrame, site, n: int, seed: int = 0
) -> pd.DataFrame:
    """현장에 가져갈 확인표. `confirmed` 열은 비워 두고, 확인한 사람이 1(고장 있었음) 또는 0(없었음)을 적는다."""
    rng = np.random.default_rng(seed)
    a1, a0, _, _ = draw_audit(L, n, rng)
    names = list(defs)
    rows = []
    for stratum, idx in (("S1", a1), ("S0", a0)):
        for i in idx:
            by = [names[k] for k in range(len(names)) if L[k][i]]
            week = int(index["week"].iloc[i])
            rows.append(
                {
                    "site": site,
                    "asset": index["asset"].iloc[i],
                    "week": week,
                    "from_day": (week + 1) * 7,
                    "to_day": (week + 1 + HORIZON_WEEKS) * 7,
                    "stratum": stratum,
                    "flagged_by": ",".join(by),
                    "confirmed": "",
                }
            )
    return (
        pd.DataFrame(rows).sample(frac=1.0, random_state=seed).reset_index(drop=True)
    )  # 확인자에게 층을 숨기려고 섞는다


def estimate_from_sample(
    defs: dict[str, Definition],
    L: np.ndarray,
    index: pd.DataFrame,
    sample: pd.DataFrame,
    beta: float = AUDIT_BETA,
    boot: int = 200,
    seed: int = 0,
) -> dict:
    """확인표(confirmed 가 채워진 것)로 정의별 정밀도, 재현율, F-beta 와 90% 구간을 추정한다."""
    s = sample.copy()
    s["confirmed"] = pd.to_numeric(s["confirmed"], errors="coerce")
    n_blank = int(s["confirmed"].isna().sum())
    s = s.dropna(subset=["confirmed"])
    if not s["confirmed"].isin([0, 1]).all():
        raise ValueError("confirmed 열은 0 또는 1 이어야 한다")
    pos = {(int(a), int(w)): i for i, (a, w) in enumerate(zip(index["asset"], index["week"], strict=True))}
    idx = []
    for a, w in zip(s["asset"], s["week"], strict=True):
        if (int(a), int(w)) not in pos:
            raise ValueError(
                f"확인표의 설비 {a}, 주 {w} 가 이 로그의 창에 없다. 같은 로그로 확인표를 만들었는지 본다"
            )
        idx.append(pos[(int(a), int(w))])
    idx_arr = np.array(idx, dtype=int)
    flagged = L.any(0)
    m1 = flagged[idx_arr]
    a1, a0 = idx_arr[m1], idx_arr[~m1]
    t1 = s["confirmed"].to_numpy()[m1]
    t0 = s["confirmed"].to_numpy()[~m1]
    if len(a0) == 0:
        raise ValueError("아무도 고장으로 표시하지 않은 창(S0)의 확인 결과가 없다. 재현율을 잴 수 없다")
    n1_pop, n0_pop = int(flagged.sum()), int((~flagged).sum())
    prec, rec = audit_stats(L, np.concatenate([t1, t0]), a1, a0, n1_pop, n0_pop)
    score = fbeta_vec(prec, rec, beta)
    lo, hi = bootstrap_interval(L, t1, t0, a1, a0, n1_pop, n0_pop, beta, np.random.default_rng(seed), boot)
    names = list(defs)
    return {
        "beta": beta,
        "n_confirmed": int(len(s)),
        "n_blank": n_blank,
        "population": {"S1": n1_pop, "S0": n0_pop},
        "sample": {"S1": int(len(a1)), "S0": int(len(a0))},
        "definitions": {
            n: {
                "precision": float(prec[k]),
                "recall": float(rec[k]),
                "score": float(score[k]),
                "lo": float(lo[k]),
                "hi": float(hi[k]),
            }
            for k, n in enumerate(names)
        },
        "pick": names[int(score.argmax())],
    }
