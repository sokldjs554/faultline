"""기록 습관 변화 감시.

고장 정의는 사이트가 작업지시를 입력하는 방식에 기대고 있다. 사이트가 습관을 바꾸면(예: 긴급 코드를 쓰지 않기 시작) 같은 정의가
다른 뜻이 되므로, 작업지시 로그만 보고 습관 변화를 잡아 현장 확인을 다시 하라고 알린다.
정답 없이 입력 로그만 쓰는 신호 세 개를 4주 단위로 세고, 앞선 기준 구간과 비교하는 CUSUM 으로 경보를 낸다.
건수가 적은 구간의 잡음은 푸아송·이항 분산으로 표준화하고, 기준 구간에서 잰 과분산만큼 더 키운다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from faultline.define.engine import SYM_CODE, _compat

SIGNALS = ("np_rate", "em_share", "unknown_share", "missing_share", "link_share")
SIGNAL_KO = {
    "np_rate": "비예방 작업지시 건수",
    "em_share": "긴급 비중",
    "unknown_share": "분류 불가 비중",
    "missing_share": "설비 번호 누락 비중",
    "link_share": "작업지시와 이어지는 민원 비중",
}
LINK_WINDOW = (-3, 14)  # 민원 날짜 기준으로 작업지시가 있어야 하는 범위(일). 정의 d3 의 근거 창과 같다


def _link_flags(w: pd.DataFrame, c: pd.DataFrame, a: pd.DataFrame) -> np.ndarray:
    """민원마다, 증상·층·설비 단서가 맞고 날짜 창 안에 든 비예방 작업지시가 하나라도 있는지."""
    cand = w[(w["wo_kind"] != "preventive") & w["asset"].notna()]
    if cand.empty or c.empty:
        return np.zeros(len(c), dtype=bool)
    pos = {int(x): i for i, x in enumerate(a["asset"].to_numpy())}
    ca = cand["asset"].astype(int).to_numpy()
    known = np.array([x in pos for x in ca])
    cand, ca = cand[known], ca[known]
    ai = np.array([pos[x] for x in ca])
    ok = _compat(a["category"].to_numpy())
    cd = cand["created_day"].to_numpy()
    c_day, c_floor = c["day"].to_numpy(), c["floor"].to_numpy()
    c_sym = c["symptom"].map(SYM_CODE).to_numpy()
    c_hint = c["hint_asset"].to_numpy(dtype=float)
    a_floor = a["floor"].to_numpy()[ai]
    m = (cd[None, :] >= c_day[:, None] - LINK_WINDOW[1]) & (cd[None, :] <= c_day[:, None] - LINK_WINDOW[0])
    m &= ok[ai][:, c_sym].T
    m &= (a_floor[None, :] == -1) | (a_floor[None, :] == c_floor[:, None])
    m &= np.isnan(c_hint)[:, None] | (c_hint[:, None] == ca[None, :])
    return m.any(1)


def binned_counts(wo_norm: pd.DataFrame, assets: pd.DataFrame, n_weeks: int, bin_weeks: int = 4, complaints: pd.DataFrame | None = None) -> dict[int, pd.DataFrame]:
    """사이트마다 구간별 건수. np 는 비예방, em 은 긴급, unk 는 분류 불가, tot 는 전체 작업지시."""
    wo = wo_norm.drop_duplicates(subset=["wo_id", "asset", "created_day", "type_raw"])
    n_bins = n_weeks // bin_weeks
    size = assets.groupby("site").size()
    out = {}
    cmp_by = {} if complaints is None else {k: v for k, v in complaints.groupby("site")}
    for site, g in wo.groupby("site"):
        b = np.clip(g["created_day"].to_numpy() // (7 * bin_weeks), 0, n_bins - 1).astype(int)
        kind = g["wo_kind"].to_numpy()
        count = lambda mask: np.bincount(b[mask], minlength=n_bins).astype(float)  # noqa: E731
        cm = np.zeros(n_bins)
        lk = np.zeros(n_bins)
        c = cmp_by.get(site)
        if c is not None and len(c):
            cb = np.clip(c["day"].to_numpy() // (7 * bin_weeks), 0, n_bins - 1).astype(int)
            flags = _link_flags(g, c, assets[assets["site"] == site])
            cm, lk = np.bincount(cb, minlength=n_bins).astype(float), np.bincount(cb[flags], minlength=n_bins).astype(float)
        out[int(site)] = pd.DataFrame(
            {
                "cm": cm,
                "lk": lk,
                "week": np.arange(n_bins) * bin_weeks,
                "exposure": float(size[site] * bin_weeks),
                "tot": count(np.ones(len(b), dtype=bool)),
                "np": count(kind != "preventive"),
                "em": count(kind == "emergency"),
                "unk": count(kind == "unknown"),
                "miss": count(g["asset"].isna().to_numpy()),
            }
        )
    return out


def _z(df: pd.DataFrame, name: str, base: slice, min_var: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """신호의 표준화 점수와 원래 값. 기준 구간의 풀링 비율을 기대값으로 쓴다."""
    if name == "np_rate":
        n, trials, value = df["np"].to_numpy(), df["exposure"].to_numpy(), df["np"].to_numpy() / df["exposure"].to_numpy()
        p0 = n[base].sum() / max(trials[base].sum(), 1e-9)
        exp, var = p0 * trials, p0 * trials
    else:
        col = {"em_share": ("em", "np"), "unknown_share": ("unk", "tot"), "missing_share": ("miss", "tot"), "link_share": ("lk", "cm")}[name]
        n, trials = df[col[0]].to_numpy(), df[col[1]].to_numpy()
        value = np.where(trials > 0, n / np.maximum(trials, 1), np.nan)
        p0 = n[base].sum() / max(trials[base].sum(), 1e-9)
        exp = p0 * trials
        var = np.where(trials > 0, p0 * (1 - p0) * trials, np.nan)
    var = np.fmax(var, min_var)  # 건수가 아주 적은 구간에서 한 건 차이가 큰 점수로 번지지 않게 한다
    with np.errstate(invalid="ignore", divide="ignore"):
        z = np.where(np.isnan(var), np.nan, (n - exp) / np.sqrt(var))
    # 과분산: 기준 구간에서 점수의 제곱 평균이 1보다 크면 그만큼 나눈다
    zb = z[base][~np.isnan(z[base])]
    phi = max(1.0, float(np.mean(zb**2))) if len(zb) else 1.0
    return z / np.sqrt(phi), value


def cusum(z: np.ndarray, base_end: int, k: float = 0.5, h: float = 5.0) -> tuple[int | None, np.ndarray]:
    """위아래 양쪽 CUSUM. 기준 구간이 끝난 뒤 처음 h 를 넘은 구간 번호와 경로를 돌려준다."""
    hi = lo = 0.0
    path = np.zeros(len(z))
    first = None
    for i, v in enumerate(z):
        if not np.isnan(v):
            hi = max(0.0, hi + v - k)
            lo = min(0.0, lo + v + k)
        path[i] = max(hi, -lo)
        if first is None and i >= base_end and path[i] > h:
            first = i
    return first, path


def monitor_sites(
    wo_norm: pd.DataFrame,
    assets: pd.DataFrame,
    n_weeks: int,
    complaints: pd.DataFrame | None = None,
    base_weeks: tuple[int, int] = (26, 78),
    bin_weeks: int = 4,
    k: float = 0.5,
    h: float = 5.0,
    min_var: float = 1.0,
) -> dict:
    """모든 사이트에 신호별 CUSUM 을 돌린다. 경보 주는 경보가 난 구간의 끝 주다(그 구간이 끝나야 값을 안다)."""
    counts = binned_counts(wo_norm, assets, n_weeks, bin_weeks, complaints)
    base = slice(base_weeks[0] // bin_weeks, base_weeks[1] // bin_weeks)
    res: dict[int, dict] = {}
    for site, df in counts.items():
        per, series = {}, {}
        for name in SIGNALS:
            z, value = _z(df, name, base, min_var)
            idx, path = cusum(z, base.stop, k, h)
            per[name] = {"alarm_week": None if idx is None else int((idx + 1) * bin_weeks), "path": [round(float(x), 3) for x in path]}
            series[name] = [None if np.isnan(x) else round(float(x), 4) for x in value]
        weeks = [v["alarm_week"] for v in per.values() if v["alarm_week"] is not None]
        res[site] = {"signals": per, "alarm_week": min(weeks) if weeks else None, "weeks": df["week"].astype(int).tolist(), "series": series}
    return {"bin_weeks": bin_weeks, "base_weeks": list(base_weeks), "k": k, "h": h, "sites": res}
