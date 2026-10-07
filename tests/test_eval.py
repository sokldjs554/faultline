import numpy as np

from faultline.define import spec
from faultline.eval import experiments as E
from faultline.eval import protocol as P


def test_fbeta_values():
    assert E._fbeta(0, 10, 10) == 0.0
    assert abs(E._fbeta(5, 10, 10, 1.0) - 0.5) < 1e-9
    # F2 는 정밀도 0.25, 재현율 1.0 에서 F1(0.4)보다 크다
    assert E._fbeta(10, 40, 10, 2.0) > E._fbeta(10, 40, 10, 1.0)


def _population(rng, n=20000):
    truth = rng.random(n) < 0.06
    # 정의 두 개: 하나는 정밀하고 재현율이 낮고, 다른 하나는 넓다
    a = (truth & (rng.random(n) < 0.4)) | (~truth & (rng.random(n) < 0.01))
    b = (truth & (rng.random(n) < 0.8)) | (~truth & (rng.random(n) < 0.1))
    return np.array([a, b]), truth


def test_audit_estimate_is_unbiased_for_precision_and_recall():
    rng = np.random.default_rng(0)
    L, T = _population(rng)
    true_p = np.array([(L[k] & T).sum() / L[k].sum() for k in range(2)])
    true_r = np.array([(L[k] & T).sum() / T.sum() for k in range(2)])
    ps, rs = [], []
    for _ in range(400):
        a1, a0, n1, n0 = E.draw_audit(L, 120, rng)
        p, r = E.audit_stats(L, np.concatenate([T[a1], T[a0]]), a1, a0, n1, n0)
        ps.append(p)
        rs.append(r)
    assert np.allclose(np.mean(ps, 0), true_p, atol=0.03)
    assert np.allclose(np.mean(rs, 0), true_r, atol=0.03)


def test_draw_audit_uses_both_strata():
    rng = np.random.default_rng(1)
    L, _ = _population(rng, 5000)
    a1, a0, n1, n0 = E.draw_audit(L, 40, rng)
    flagged = L.any(0)
    assert flagged[a1].all() and not flagged[a0].any()
    assert n1 == flagged.sum() and n0 == (~flagged).sum()
    assert len(a1) + len(a0) == 40


def test_exp_audit_regret_shrinks_with_more_checks(prep):
    defs = spec.builtin()
    res = E.exp_audit(prep, defs, n_grid=(10, 320), reps=15, seed=0)
    assert res["regret"][1] < res["regret"][0]
    assert all(s["best"] in defs for s in res["sites"])


def test_window_quality_matches_definition_breadth(prep):
    q = E.window_quality(prep, spec.builtin())
    assert q["d2_corrective"]["recall"] > q["d1_emergency"]["recall"]
    assert q["d1_emergency"]["precision"] > q["d2_corrective"]["precision"]
    assert all(0 <= v <= 1 for d in q.values() for v in d.values())


def test_label_matrix_uses_only_records_entered_by_the_cutoff(prep):
    d1 = spec.builtin()["d1_emergency"]
    now = P.labels_for(prep, d1, E.AS_OF)
    later = P.labels_for(prep, d1, None)
    ok = ~np.isnan(now) & ~np.isnan(later)
    assert (later[ok] >= now[ok]).all()  # 기록이 더 쌓이면 양성은 늘기만 한다


def test_jaccard():
    a = np.array([1, 1, 0, 0], dtype=bool)
    b = np.array([1, 0, 1, 0], dtype=bool)
    assert abs(P.jaccard(a, b) - 1 / 3) < 1e-9 and P.jaccard(a, a) == 1.0


def test_truth_oracle_beats_models(prep):
    """정답 손상 상태를 아는 오라클은 기록만 보는 모형보다 낫다(실험 구조가 맞는지 확인)."""
    te = prep.test_rows
    D = prep.world.meta["damage"]
    oracle = D[prep.fs.asset_idx[te], np.minimum(prep.fs.week[te] + 1, D.shape[1] - 1)]
    r_o, _ = E._metrics(prep, oracle, None)
    r_m, _ = E._metrics(prep, E._score(prep, prep.y_truth), None)
    assert r_o["truth_auc"] > r_m["truth_auc"]
