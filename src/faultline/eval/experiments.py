"""실험들. 각 함수는 JSON 으로 저장할 수 있는 딕셔너리를 돌려준다."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from faultline.define.spec import Definition
from faultline.eval import protocol as P
from faultline.eval.labels import match_incidents, public, window_labels
from faultline.models import fit
from faultline.quality.contract import normalize_wo, quality_report

AS_OF = P.CUTOFF_WEEK * 7 - 1
AUDIT_BETA = (
    2.0  # 현장 확인으로 정의를 고를 때 재현율을 정밀도보다 두 배 무겁게 본다(근거: exp_metric_validity)
)


def _site_auc(scores: np.ndarray, y: np.ndarray, site: np.ndarray) -> float:
    """사이트 안에서만 비교한 AUC 평균(양성 수 가중). 사이트마다 다른 기록 습관을 맞히는 효과를 뺀다."""
    num = den = 0.0
    for s in np.unique(site):
        m = (site == s) & ~np.isnan(y)
        yy = y[m]
        if 0 < yy.sum() < len(yy):
            w = yy.sum()
            num += w * roc_auc_score(yy, scores[m])
            den += w
    return float(num / den) if den else float("nan")


def _score(prep: P.Prepared, y_mat: np.ndarray, mlp: bool = False, rows: np.ndarray | None = None):
    tr = prep.train_rows if rows is None else rows
    y_tr = P.rows_of(prep, y_mat, tr)
    ok = ~np.isnan(y_tr)
    X = prep.fs.X.iloc[tr[ok]]
    if mlp:
        m = fit.MlpModel().fit(X, y_tr[ok])
        return m.predict(prep.fs.X.iloc[prep.test_rows])
    m = fit.fit_hgb(X, y_tr[ok])
    return fit.predict_hgb(m, prep.fs.X.iloc[prep.test_rows])


def _metrics(prep: P.Prepared, scores: np.ndarray, own: np.ndarray | None):
    te = prep.test_rows
    r, sel = P.evaluate(prep, scores, te, own)
    yt = P.rows_of(prep, prep.y_truth, te)
    r["truth_site_auc"] = _site_auc(scores, yt, prep.fs.site[te])
    if own is not None:
        r["own_site_auc"] = _site_auc(scores, P.rows_of(prep, own, te), prep.fs.site[te])
    return r, sel


# ---------------------------------------------------------------- 1. 라벨 품질
def exp_labels(prep: P.Prepared, defs: dict[str, Definition], tol: int = 14) -> dict:
    w = prep.world
    arch = w.sites.set_index("site")["archetype"]
    out = {"definitions": {}, "n_failures": int(len(w.failures))}
    for name, d in defs.items():
        res = P.incidents_for(prep, d)
        inc = res.incidents
        m = match_incidents(inc, w.failures, tol)
        by_arch = {}
        for a in arch.unique():
            sites = arch[arch == a].index
            ma = match_incidents(
                inc[inc["site"].isin(sites)], w.failures[w.failures["site"].isin(sites)], tol
            )
            by_arch[a] = public(ma)
        by_site = []
        for s in sorted(arch.index):
            ms = match_incidents(inc[inc["site"] == s], w.failures[w.failures["site"] == s], tol)
            by_site.append({"site": int(s), "archetype": arch[s], **public(ms)})
        out["definitions"][name] = {
            "overall": public(m),
            "by_archetype": by_arch,
            "by_site": by_site,
            "evidence": inc["evidence"].value_counts().to_dict(),
            "stats": res.stats,
        }
    return out


# ---------------------------------------------------------------- 2. 정의 민감도
def exp_sensitivity(
    prep: P.Prepared,
    defs: dict[str, Definition],
    mlp: tuple[str, ...] = ("d1_emergency", "d2_corrective", "d3_corroborated"),
) -> dict:
    te = prep.test_rows
    out: dict = {"models": {}}
    sels: dict[str, np.ndarray] = {}
    for name, d in defs.items():
        y = P.labels_for(prep, d, AS_OF)
        own_full = P.labels_for(prep, d, None)
        s = _score(prep, y)
        r, sel = _metrics(prep, s, own_full)
        r["train_positive_rate"] = float(np.nanmean(P.rows_of(prep, y, prep.train_rows)))
        out["models"][name] = {"hgb": r}
        sels[name] = sel
    s = _score(prep, prep.y_truth)
    r, sel = _metrics(prep, s, None)
    out["models"]["truth"] = {"hgb": r}
    sels["truth"] = sel
    # 손상 상태를 아는 오라클(시뮬레이터 안에서만 가능)
    D = prep.world.meta["damage"]
    nxt = np.minimum(prep.fs.week[te] + 1, D.shape[1] - 1)
    orc = D[prep.fs.asset_idx[te], nxt]
    r, sel = _metrics(prep, orc, None)
    out["models"]["oracle"] = {"hgb": r}
    sels["oracle"] = sel
    for name in mlp:
        y = P.labels_for(prep, defs[name], AS_OF)
        s = _score(prep, y, mlp=True)
        r, _ = _metrics(prep, s, P.labels_for(prep, defs[name], None))
        out["models"][name]["mlp"] = r
    s = _score(prep, prep.y_truth, mlp=True)
    r, _ = _metrics(prep, s, None)
    out["models"]["truth"]["mlp"] = r
    names = [*defs, "truth"]
    out["overlap"] = {"names": names, "matrix": [[P.jaccard(sels[a], sels[b]) for b in names] for a in names]}
    out["topk"] = P.TOPK
    return out


# ---------------------------------------------------------------- 3. 현장 확인 표본 수
def _site_windows(prep: P.Prepared, defs: dict[str, Definition], site: int):
    idx = np.flatnonzero(prep.world.assets["site"].to_numpy() == site)
    lo, hi = P.T_MIN, prep.n_weeks - P.HORIZON - 1
    mats = [P.labels_for(prep, d, None)[idx][:, lo : hi + 1].ravel() for d in defs.values()]
    truth = prep.y_truth[idx][:, lo : hi + 1].ravel()
    return np.array(mats, dtype=bool), truth.astype(bool)


def _fbeta(tp: float, pred: float, pos: float, beta: float = 1.0) -> float:
    if tp <= 0 or pred <= 0 or pos <= 0:
        return 0.0
    p, r = tp / pred, tp / pos
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r)


def audit_stats(
    L: np.ndarray, truth_sample: np.ndarray, idx_s1: np.ndarray, idx_s0: np.ndarray, n1_pop: int, n0_pop: int
) -> tuple[np.ndarray, np.ndarray]:
    """층화 표본에서 정의별 정밀도와 재현율을 추정한다.

    하나라도 고장으로 표시한 창(S1)과 아무도 표시하지 않은 창(S0)에서 따로 뽑고, 층의 크기로 가중한다(Horvitz-Thompson).
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


def _fb(prec: np.ndarray, rec: np.ndarray, beta: float) -> np.ndarray:
    b2 = beta * beta
    den = b2 * prec + rec
    return np.where(den > 0, (1 + b2) * prec * rec / np.where(den > 0, den, 1.0), 0.0)


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
    return _fb(prec, rec, beta)


def draw_audit(
    L: np.ndarray, n: int, rng: np.random.Generator, share_s1: float = 0.5
) -> tuple[np.ndarray, np.ndarray, int, int]:
    """현장에서 확인할 창을 뽑는다. 절반은 어느 정의든 고장으로 표시한 창에서, 나머지는 아무도 표시하지 않은 창에서."""
    flagged = L.any(0)
    s1, s0 = np.flatnonzero(flagged), np.flatnonzero(~flagged)
    n1 = min(max(int(round(n * share_s1)), 1), len(s1))
    n0 = min(max(n - n1, 1), len(s0))
    a1 = rng.choice(s1, n1, replace=False) if len(s1) else np.array([], dtype=int)
    a0 = rng.choice(s0, n0, replace=False)
    return a1.astype(int), a0.astype(int), len(s1), len(s0)


def exp_audit_demo(
    prep: P.Prepared,
    defs: dict[str, Definition],
    n_grid=(10, 20, 40, 80, 160, 320),
    boot: int = 200,
    seed: int = 0,
    beta: float = AUDIT_BETA,
) -> dict:
    """사이트마다, 확인 건수마다 한 번 뽑은 표본으로 정의별 점수를 추정하고 부트스트랩 구간과 정답을 함께 낸다."""
    rng = np.random.default_rng(seed)
    names = list(defs)
    out = {"names": names, "n_grid": list(n_grid), "beta": beta, "sites": {}}
    arch = prep.world.sites.set_index("site")["archetype"]
    for s in sorted(prep.world.sites["site"]):
        L, T = _site_windows(prep, defs, s)
        truth = {
            "precision": [float((L[k] & T).sum() / max(L[k].sum(), 1)) for k in range(len(names))],
            "recall": [float((L[k] & T).sum() / max(T.sum(), 1)) for k in range(len(names))],
        }
        truth["score"] = [
            float(_fbeta((L[k] & T).sum(), L[k].sum(), T.sum(), beta)) for k in range(len(names))
        ]
        item = {
            "archetype": arch[s],
            "truth": truth,
            "windows": int(L.shape[1]),
            "flagged": int(L.any(0).sum()),
            "by_n": {},
        }
        for n in n_grid:
            a1, a0, n1p, n0p = draw_audit(L, n, rng)
            sample = np.concatenate([T[a1], T[a0]])
            prec, rec = audit_stats(L, sample, a1, a0, n1p, n0p)
            est = _fb(prec, rec, beta)
            boots = np.zeros((boot, len(names)))
            for b in range(boot):
                i1 = rng.integers(0, max(len(a1), 1), len(a1)) if len(a1) else np.array([], dtype=int)
                i0 = rng.integers(0, len(a0), len(a0))
                bs = np.concatenate([T[a1][i1], T[a0][i0]]) if len(a1) else T[a0][i0]
                boots[b] = _fb(*audit_stats(L, bs, a1[i1], a0[i0], n1p, n0p), beta)
            item["by_n"][str(n)] = {
                "n": int(len(a1) + len(a0)),
                "precision": prec.tolist(),
                "recall": rec.tolist(),
                "score": est.tolist(),
                "lo": np.percentile(boots, 5, axis=0).tolist(),
                "hi": np.percentile(boots, 95, axis=0).tolist(),
                "pick": names[int(est.argmax())],
            }
        item["best"] = names[int(np.argmax(truth["score"]))]
        out["sites"][str(s)] = item
    return out


def exp_audit(
    prep: P.Prepared,
    defs: dict[str, Definition],
    n_grid=(10, 20, 40, 80, 160, 320),
    reps: int = 300,
    seed: int = 0,
    share_s1: float = 0.5,
    beta: float = AUDIT_BETA,
) -> dict:
    rng = np.random.default_rng(seed)
    names = list(defs)
    res = {"n_grid": list(n_grid), "names": names, "beta": beta, "sites": []}
    exact = np.zeros((len(prep.world.sites), len(n_grid)))
    near = np.zeros_like(exact)
    regret = np.zeros_like(exact)
    for si, s in enumerate(sorted(prep.world.sites["site"])):
        L, T = _site_windows(prep, defs, s)
        f1_true = np.array([_fbeta((L[k] & T).sum(), L[k].sum(), T.sum(), beta) for k in range(len(names))])
        best = int(f1_true.argmax())
        for ni, n in enumerate(n_grid):
            ok = nr = rg = 0.0
            for _ in range(reps):
                a1, a0, n1p, n0p = draw_audit(L, n, rng, share_s1)
                est = audit_estimate(L, np.concatenate([T[a1], T[a0]]), a1, a0, n1p, n0p, beta)
                pick = int(est.argmax())  # 추정이 같은 값이면 처음 것을 고른다(정의 순서)
                ok += pick == best
                nr += f1_true[pick] >= f1_true[best] - 0.02
                rg += f1_true[best] - f1_true[pick]
            exact[si, ni], near[si, ni], regret[si, ni] = ok / reps, nr / reps, rg / reps
        res["sites"].append(
            {
                "site": int(s),
                "archetype": prep.world.sites.set_index("site").loc[s, "archetype"],
                "best": names[best],
                "score_true": {n: float(v) for n, v in zip(names, f1_true, strict=True)},
            }
        )
    res["p_exact"] = exact.mean(0).tolist()
    res["p_near"] = near.mean(0).tolist()
    res["regret"] = regret.mean(0).tolist()
    res["by_site_near"] = near.tolist()
    need = [n for n, p in zip(n_grid, res["p_near"], strict=True) if p >= 0.9]
    res["n_for_90pct"] = int(need[0]) if need else None
    return res


# ---------------------------------------------------------------- 4. 고객 맞춤 정의
def _assigned_labels(
    prep: P.Prepared, defs: dict[str, Definition], assign: dict[int, str], as_of: int | None
) -> np.ndarray:
    """사이트마다 다른 정의를 적용한 라벨 행렬."""
    mats = {name: P.labels_for(prep, defs[name], as_of) for name in set(assign.values())}
    site = prep.world.assets["site"].to_numpy()
    y = np.full(prep.y_truth.shape, np.nan)
    for s, name in assign.items():
        y[site == s] = mats[name][site == s]
    return y


def pick_with_audit(
    prep: P.Prepared,
    defs: dict[str, Definition],
    n: int,
    seed: int,
    share_s1: float = 0.5,
    beta: float = AUDIT_BETA,
) -> dict[int, str]:
    rng = np.random.default_rng(seed)
    names = list(defs)
    out = {}
    for s in sorted(prep.world.sites["site"]):
        L, T = _site_windows(prep, defs, s)
        a1, a0, n1p, n0p = draw_audit(L, n, rng, share_s1)
        est = audit_estimate(L, np.concatenate([T[a1], T[a0]]), a1, a0, n1p, n0p, beta)
        out[int(s)] = names[int(est.argmax())]
    return out


def exp_custom(
    prep: P.Prepared,
    defs: dict[str, Definition],
    audit: dict,
    audit_ns: tuple[int, ...] = (40, 80),
    draws: int = 3,
    beta: float = AUDIT_BETA,
) -> dict:
    """사이트마다 정의를 달리 고르면 모형이 나아지는가."""
    sites = sorted(prep.world.sites["site"])
    oracle = {int(r["site"]): r["best"] for r in audit["sites"]}
    strategies: dict[str, list[dict[int, str]]] = {
        f"fixed_{n}": [{s: n for s in sites}]
        for n in ("d1_emergency", "d2_corrective", "d3_corroborated")
        if n in defs
    }
    for n in audit_ns:
        strategies[f"audit_{n}"] = [pick_with_audit(prep, defs, n, 100 + i, beta=beta) for i in range(draws)]
    strategies["oracle"] = [oracle]
    out = {"audit_ns": list(audit_ns), "beta": beta, "strategies": {}, "assignments": {}}
    keys = ("truth_auc", "truth_ap", "truth_per100", "truth_site_auc")
    for label, assigns in strategies.items():
        rs = []
        for a in assigns:
            y = _assigned_labels(prep, defs, a, AS_OF)
            r, _ = _metrics(prep, _score(prep, y), None)
            rs.append(r)
        out["strategies"][label] = {k: float(np.mean([r[k] for r in rs])) for k in keys}
        out["assignments"][label] = {str(s): v for s, v in assigns[0].items()}
    r, _ = _metrics(prep, _score(prep, prep.y_truth), None)
    out["strategies"]["truth"] = {k: float(r[k]) for k in keys}
    return out


# ---------------------------------------------------------------- 5. 라벨 지연
def exp_maturity(prep: P.Prepared, defs: dict[str, Definition]) -> dict:
    w = prep.world
    arch = w.sites.set_index("site")["archetype"]
    truth = w.wo_truth[w.wo_truth["kind"] == "failure"].drop_duplicates("failure_id")
    wo = w.wo.drop_duplicates("wo_id").merge(truth, on="wo_id")
    wo = wo.merge(w.failures[["failure_id", "day"]], on="failure_id")
    wo["lag"] = wo["created_day"] - wo["day"]
    wo["arch"] = wo["site"].map(arch)
    curve = {}
    for a, g in wo.groupby("arch"):
        curve[a] = {
            "median": float(g["lag"].median()),
            "p90": float(g["lag"].quantile(0.9)),
            "within": {str(d): float((g["lag"] <= d).mean()) for d in (3, 7, 14, 28, 56)},
        }
    # 학습 라벨이 덜 성숙했을 때의 영향(정의: d3)
    d = defs["d3_corroborated"]
    te = prep.test_rows
    variants = {}
    for label, as_of, end in (
        ("지금까지 입력된 기록으로 학습", AS_OF, P.TRAIN_END),
        ("최근 4주 행은 학습에서 제외", AS_OF, P.TRAIN_END - 4),
        ("충분히 기다린 라벨로 학습", None, P.TRAIN_END),
    ):
        y = P.labels_for(prep, d, as_of)
        rows = prep.rows(P.T_MIN, end)
        s = _score(prep, y, rows=rows)
        r, _ = _metrics(prep, s, None)
        late = np.isin(prep.fs.site[te], arch[arch.isin(["늦게 입력"])].index)
        yt = P.rows_of(prep, prep.y_truth, te)
        r["truth_auc_late_sites"] = float(roc_auc_score(yt[late], s[late])) if late.any() else float("nan")
        r["truth_ap_late_sites"] = (
            float(average_precision_score(yt[late], s[late])) if late.any() else float("nan")
        )
        variants[label] = {
            k: r[k]
            for k in ("truth_auc", "truth_ap", "truth_per100", "truth_auc_late_sites", "truth_ap_late_sites")
        }
    return {"entry_delay_by_archetype": curve, "training_variants": variants}


# ---------------------------------------------------------------- 6. 데이터 품질
def exp_quality(prep: P.Prepared, defs: dict[str, Definition]) -> dict:
    w = prep.world
    raw = pd.concat([normalize_wo(g, None) for _, g in w.wo.groupby("site")], ignore_index=True)
    rep = quality_report(w.wo, w.complaints, w.assets, None, w.cfg.weeks)
    book = P.code_books(w)
    rep_book = quality_report(w.wo, w.complaints, w.assets, book, w.cfg.weeks)
    code_sites = [s for s in book]
    d1 = defs["d1_emergency"]
    no_book = P.apply_definition(d1, raw, w.complaints, w.assets).incidents
    with_book = P.incidents_for(prep, d1).incidents
    f_cs = w.failures[w.failures["site"].isin(code_sites)]
    m0 = match_incidents(no_book[no_book["site"].isin(code_sites)], f_cs)
    m1 = match_incidents(with_book[with_book["site"].isin(code_sites)], f_cs)
    return {
        "report_without_code_book": rep,
        "report_with_code_book": rep_book,
        "code_book_effect_d1": {"sites": code_sites, "without": public(m0), "with": public(m1)},
    }


# ---------------------------------------------------------------- 7. 여러 시드 요약
def window_quality(prep: P.Prepared, defs: dict[str, Definition]) -> dict:
    """정의별 라벨을 창(설비 x 주) 단위로 정답과 맞춘 정밀도·재현율. 현장 확인이 재는 것과 같은 단위다."""
    lo, hi = P.T_MIN, prep.n_weeks - P.HORIZON - 1
    T = prep.y_truth[:, lo : hi + 1].ravel().astype(bool)
    out = {}
    for name, d in defs.items():
        L = P.labels_for(prep, d, None)[:, lo : hi + 1].ravel().astype(bool)
        tp = float((L & T).sum())
        prec, rec = tp / max(L.sum(), 1), tp / max(T.sum(), 1)
        out[name] = {
            "precision": prec,
            "recall": rec,
            "f1": _fbeta(tp, L.sum(), T.sum(), 1.0),
            "f2": _fbeta(tp, L.sum(), T.sum(), 2.0),
            "positive_rate": float(L.mean()),
        }
    return out


def exp_seed(
    seed: int,
    uniform: bool = False,
    audit_ns: tuple[int, ...] = (40, 80),
    draws: int = 3,
    strategies: bool = True,
) -> dict:
    """한 시드의 세계에서 정의별 라벨 품질, 모형 성능, 사이트별 정의 선택 전략을 잰다."""
    from faultline.define import spec
    from faultline.sim.world import WorldConfig, simulate

    defs = spec.builtin()
    world = simulate(WorldConfig(seed=seed, uniform_habit=uniform))
    prep = P.prepare(world)
    out: dict = {
        "seed": seed,
        "uniform": uniform,
        "n_failures": int(len(world.failures)),
        "window": window_quality(prep, defs),
        "models": {},
    }
    te = prep.test_rows
    for name, d in defs.items():
        y = P.labels_for(prep, d, AS_OF)
        r, _ = _metrics(prep, _score(prep, y), P.labels_for(prep, d, None))
        out["models"][name] = {
            k: r[k] for k in ("truth_auc", "truth_ap", "truth_per100", "truth_site_auc", "own_auc", "own_ap")
        }
    r, _ = _metrics(prep, _score(prep, prep.y_truth), None)
    out["models"]["truth"] = {k: r[k] for k in ("truth_auc", "truth_ap", "truth_per100", "truth_site_auc")}
    D = world.meta["damage"]
    orc = D[prep.fs.asset_idx[te], np.minimum(prep.fs.week[te] + 1, D.shape[1] - 1)]
    r, _ = _metrics(prep, orc, None)
    out["models"]["oracle"] = {k: r[k] for k in ("truth_auc", "truth_ap", "truth_per100", "truth_site_auc")}
    if strategies and not uniform:
        aud = exp_audit(prep, defs, n_grid=(10, 20, 40, 80, 160, 320), reps=150, seed=seed)
        out["audit"] = {k: aud[k] for k in ("n_grid", "p_exact", "p_near", "regret", "n_for_90pct")}
        out["custom"] = exp_custom(prep, defs, aud, audit_ns, draws)
    return out


def exp_metric_validity(seed_runs: list[dict]) -> dict:
    """정의의 라벨 지표 중 무엇이 그 라벨로 학습한 모형의 진짜 성능과 함께 움직이는가(시드별 순위 상관)."""
    from scipy.stats import spearmanr

    metrics = ("precision", "recall", "f1", "f2", "positive_rate")
    out: dict = {"metrics": {m: [] for m in metrics}, "seeds": [r["seed"] for r in seed_runs]}
    for run in seed_runs:
        names = list(run["window"])
        auc = [run["models"][n]["truth_auc"] for n in names]
        for m in metrics:
            out["metrics"][m].append(float(spearmanr([run["window"][n][m] for n in names], auc)[0]))
    out["mean"] = {m: float(np.mean(v)) for m, v in out["metrics"].items()}
    return out


# ---------------------------------------------------------------- 8. 기록 습관 변화 감시
SHIFT_WEEK = 100
SHIFTS = (
    (0, SHIFT_WEEK, "긴급 안 씀"),
    (4, SHIFT_WEEK, "표준"),
    (6, SHIFT_WEEK, "입력 누락"),
    (12, SHIFT_WEEK, "긴급 남용"),
)


def exp_drift(
    seeds: tuple[int, ...] = (7, 11, 23, 31, 47), h: float = 10.0, keep_series_for: int = 7
) -> dict:
    """습관이 바뀐 사이트를 로그만으로 얼마나 빨리, 얼마나 정확히 잡는가. 바뀌지 않은 세계에서 거짓 경보도 센다."""
    from faultline.define import spec
    from faultline.monitor.drift import monitor_sites
    from faultline.sim.world import WorldConfig, simulate

    defs = spec.builtin()
    shifted = {s for s, _, _ in SHIFTS}
    runs, series = [], None
    day0 = SHIFT_WEEK * 7
    for seed in seeds:
        rec: dict = {"seed": seed, "detected": [], "false_alarm_sites": 0, "quiet_site_runs": 0}
        # 대조: 습관이 바뀌지 않는 세계
        w0 = simulate(WorldConfig(seed=seed))
        p0 = P.prepare(w0)
        m0 = monitor_sites(p0.wo_norm, w0.assets, w0.cfg.weeks, w0.complaints, h=h)
        rec["control_alarms"] = sum(v["alarm_week"] is not None for v in m0["sites"].values())
        rec["control_sites"] = len(m0["sites"])
        # 사이트 몇 곳이 습관을 바꾸는 세계
        w1 = simulate(WorldConfig(seed=seed, shifts=SHIFTS))
        p1 = P.prepare(w1)
        m1 = monitor_sites(p1.wo_norm, w1.assets, w1.cfg.weeks, w1.complaints, h=h)
        for site, v in m1["sites"].items():
            aw = v["alarm_week"]
            if site in shifted:
                fired = [] if aw is None else [n for n, x in v["signals"].items() if x["alarm_week"] == aw]
                rec["detected"].append(
                    {
                        "site": site,
                        "to": next(t for s2, _, t in SHIFTS if s2 == site),
                        "alarm_week": aw,
                        "delay_weeks": None if aw is None or aw < SHIFT_WEEK else aw - SHIFT_WEEK,
                        "false_before": aw is not None and aw < SHIFT_WEEK,
                        "signals": fired,
                    }
                )
            else:
                rec["quiet_site_runs"] += 1
                rec["false_alarm_sites"] += aw is not None
        # 습관이 바뀐 뒤 라벨 품질이 얼마나 떨어지는가
        lab = {}
        for name in ("d1_emergency", "d2_corrective", "d3_corroborated"):
            inc = P.incidents_for(p1, defs[name]).incidents
            row = {}
            for tag, sel_i, sel_f in (
                ("before", inc["day"] < day0, w1.failures["day"] < day0),
                ("after", inc["day"] >= day0, w1.failures["day"] >= day0),
            ):
                m = match_incidents(
                    inc[sel_i & inc["site"].isin(shifted)],
                    w1.failures[sel_f & w1.failures["site"].isin(shifted)],
                )
                row[tag] = {k: m[k] for k in ("precision", "recall", "f1")}
            lab[name] = row
        rec["label_quality_shifted_sites"] = lab
        runs.append(rec)
        if seed == keep_series_for:
            series = {
                "weeks": m1["sites"][0]["weeks"],
                "sites": {
                    str(k): {"signals": v["signals"], "series": v["series"], "alarm_week": v["alarm_week"]}
                    for k, v in m1["sites"].items()
                },
                "shifts": [list(x) for x in SHIFTS],
            }
    dets = [d for r in runs for d in r["detected"]]
    found = [d for d in dets if d["delay_weeks"] is not None]
    quiet_runs = sum(r["quiet_site_runs"] for r in runs)
    out = {
        "h": h,
        "shift_week": SHIFT_WEEK,
        "seeds": list(seeds),
        "runs": runs,
        "shifts_total": len(dets),
        "shifts_detected": len(found),
        "delay_median_weeks": float(np.median([d["delay_weeks"] for d in found])) if found else None,
        "delay_max_weeks": int(max(d["delay_weeks"] for d in found)) if found else None,
        "false_alarm_site_runs": int(
            sum(r["false_alarm_sites"] for r in runs) + sum(r["control_alarms"] for r in runs)
        ),
        "quiet_site_runs": int(quiet_runs + sum(r["control_sites"] for r in runs)),
        "by_target": {},
        "series": series,
    }
    for tgt in sorted({d["to"] for d in dets}):
        g = [d for d in dets if d["to"] == tgt]
        out["by_target"][tgt] = {
            "n": len(g),
            "detected": sum(d["delay_weeks"] is not None for d in g),
            "delays": [d["delay_weeks"] for d in g if d["delay_weeks"] is not None],
        }
    return out


# ---------------------------------------------------------------- 9. 전조 신호 가정에 대한 민감도
def exp_robustness(
    strengths: tuple[float, ...] = (0.0, 0.5, 1.0), seeds: tuple[int, ...] = (7, 11, 23)
) -> dict:
    """시뮬레이터는 손상이 클수록 경미한 시정 작업지시와 약한 민원이 늘어난다고 가정한다. 이 전조가 약해지면 정의 순위가 바뀌는지 본다."""
    from faultline.define import spec
    from faultline.sim.world import WorldConfig, simulate

    defs = {
        k: v for k, v in spec.builtin().items() if k in ("d1_emergency", "d2_corrective", "d3_corroborated")
    }
    base = WorldConfig()
    out: dict = {"strengths": list(strengths), "seeds": list(seeds), "results": {}}
    for st in strengths:
        rows = []
        for seed in seeds:
            w = simulate(
                WorldConfig(seed=seed, minor_gain=base.minor_gain * st, pre_cmp_rate=base.pre_cmp_rate * st)
            )
            prep = P.prepare(w)
            row = {"seed": seed}
            for name, d in defs.items():
                r, _ = _metrics(prep, _score(prep, P.labels_for(prep, d, AS_OF)), None)
                row[name] = r["truth_auc"]
            r, _ = _metrics(prep, _score(prep, prep.y_truth), None)
            row["truth"] = r["truth_auc"]
            rows.append(row)
        out["results"][str(st)] = {k: float(np.mean([r[k] for r in rows])) for k in (*defs, "truth")}
        out["results"][str(st)]["seeds"] = rows
    return out


__all__ = [
    "exp_labels",
    "exp_sensitivity",
    "exp_audit",
    "exp_custom",
    "exp_maturity",
    "exp_quality",
    "exp_seed",
    "exp_metric_validity",
    "exp_drift",
    "exp_robustness",
    "window_labels",
]
