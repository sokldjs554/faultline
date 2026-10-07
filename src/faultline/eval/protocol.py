"""실험 공통 틀: 시간 분할, 정의별 라벨, 평가 지표.

학습은 앞쪽 주, 평가는 뒤쪽 주로 나눈다. 평가는 정의가 만든 라벨(겉보기)과 진짜 고장(정답) 두 가지로 한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from faultline.define.engine import apply_definition
from faultline.define.spec import Definition
from faultline.eval.labels import window_labels
from faultline.models.features import FeatureSet, build_features
from faultline.quality.contract import normalize_wo
from faultline.sim.world import CODE_SCHEMES, World

HORIZON = 4
T_MIN = 26
TRAIN_END = 95  # 학습 행의 마지막 판단 주
CUTOFF_WEEK = 100  # 학습 라벨은 이 주 직전까지 입력된 기록으로 만든다
TEST_START = 104
TOPK = 5


def true_code_book(scheme: str) -> dict[str, str]:
    return {v: k for k, v in CODE_SCHEMES[scheme].items()}


def code_books(world: World) -> dict[int, dict[str, str]]:
    """코드 체계가 'code' 인 사이트는 온보딩에서 코드표를 받았다고 본다."""
    out = {}
    for _, r in world.sites.iterrows():
        if r["habit_scheme"] == "code":
            out[int(r["site"])] = true_code_book("code")
    return out


@dataclass
class Prepared:
    world: World
    wo_norm: pd.DataFrame
    fs: FeatureSet
    y_truth: np.ndarray  # 설비 x 주
    incidents: dict = field(default_factory=dict)  # (정의 이름, as_of) -> DefinitionResult

    @property
    def n_weeks(self) -> int:
        return self.world.cfg.weeks

    def rows(self, lo: int, hi: int) -> np.ndarray:
        return np.flatnonzero((self.fs.week >= lo) & (self.fs.week <= hi))

    @property
    def train_rows(self) -> np.ndarray:
        return self.rows(T_MIN, TRAIN_END)

    @property
    def test_rows(self) -> np.ndarray:
        return self.rows(TEST_START, self.n_weeks - HORIZON - 1)


def prepare(world: World, code_book_by_site: dict[int, dict[str, str]] | None = None) -> Prepared:
    books = code_books(world) if code_book_by_site is None else code_book_by_site
    parts = [normalize_wo(g, books.get(int(s))) for s, g in world.wo.groupby("site")]
    wo_norm = pd.concat(parts, ignore_index=True)
    fs = build_features(world.assets, wo_norm, world.complaints, world.pm, world.cfg.weeks, T_MIN)
    y_truth = window_labels(world.failures, world.assets, world.cfg.weeks, HORIZON)
    return Prepared(world, wo_norm, fs, y_truth)


def incidents_for(prep: Prepared, defn: Definition, as_of_day: int | None = None):
    key = (defn.name, as_of_day)
    if key not in prep.incidents:
        w = prep.world
        prep.incidents[key] = apply_definition(defn, prep.wo_norm, w.complaints, w.assets, as_of_day)
    return prep.incidents[key]


def labels_for(prep: Prepared, defn: Definition, as_of_day: int | None = None) -> np.ndarray:
    inc = incidents_for(prep, defn, as_of_day).incidents
    return window_labels(inc, prep.world.assets, prep.n_weeks, HORIZON)


def rows_of(prep: Prepared, mat: np.ndarray, rows: np.ndarray) -> np.ndarray:
    return mat[prep.fs.asset_idx[rows], prep.fs.week[rows]]


def topk_flags(scores: np.ndarray, site: np.ndarray, week: np.ndarray, k: int = TOPK) -> np.ndarray:
    """사이트·주마다 점수 상위 k 개를 고른 표시."""
    df = pd.DataFrame({"s": scores, "site": site, "week": week})
    rank = df.groupby(["site", "week"])["s"].rank(ascending=False, method="first")
    return (rank <= k).to_numpy()


def evaluate(
    prep: Prepared, scores: np.ndarray, rows: np.ndarray, own: np.ndarray | None = None, k: int = TOPK
) -> dict:
    """점수를 평가 행에서 채점한다. 정답(진짜 고장)과 겉보기(정의 라벨) 둘 다 낸다."""
    yt = rows_of(prep, prep.y_truth, rows)
    sel = topk_flags(scores, prep.fs.site[rows], prep.fs.week[rows], k)
    out = {
        "truth_auc": float(roc_auc_score(yt, scores)),
        "truth_ap": float(average_precision_score(yt, scores)),
        "truth_per100": float(100 * yt[sel].sum() / max(sel.sum(), 1)),
        "base_rate": float(yt.mean()),
        "random_per100": float(100 * yt.mean()),
    }
    if own is not None:
        yo = rows_of(prep, own, rows)
        ok = ~np.isnan(yo)
        if ok.sum() and 0 < yo[ok].sum() < ok.sum():
            out["own_auc"] = float(roc_auc_score(yo[ok], scores[ok]))
            out["own_ap"] = float(average_precision_score(yo[ok], scores[ok]))
            out["own_rate"] = float(yo[ok].mean())
        else:
            out["own_auc"] = out["own_ap"] = float("nan")
            out["own_rate"] = float(np.nanmean(yo)) if ok.sum() else float("nan")
    return out, sel


def jaccard(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / max((a | b).sum(), 1))
