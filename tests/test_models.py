import numpy as np
import pytest

from faultline.eval import protocol as P
from faultline.models import fit
from faultline.models.features import FEATURES, build_features


def test_feature_matrix_shape(prep):
    fs = prep.fs
    n_assets, n_weeks = len(prep.world.assets), prep.world.cfg.weeks
    assert fs.X.shape == (n_assets * (n_weeks - P.T_MIN), len(FEATURES))
    assert list(fs.X.columns) == FEATURES and not fs.X.isna().any().any()


def test_features_do_not_look_ahead(prep):
    """t 주까지의 기록만 남겨도 t 주 이하 행의 특징은 그대로여야 한다."""
    w = prep.world
    t = 80
    cut = (t + 1) * 7
    wo = prep.wo_norm[prep.wo_norm["created_day"] < cut]
    cm = w.complaints[w.complaints["day"] < cut]
    pm = w.pm[w.pm["day"] < cut]
    fs2 = build_features(w.assets, wo, cm, pm, w.cfg.weeks, P.T_MIN)
    rows = np.flatnonzero(prep.fs.week <= t)
    a = prep.fs.X.iloc[rows].reset_index(drop=True)
    b = fs2.X.iloc[rows].reset_index(drop=True)
    assert np.allclose(a.to_numpy(float), b.to_numpy(float), equal_nan=True)


def test_time_split_keeps_train_before_test(prep):
    assert prep.fs.week[prep.train_rows].max() == P.TRAIN_END
    assert prep.fs.week[prep.test_rows].min() == P.TEST_START
    assert P.CUTOFF_WEEK <= P.TEST_START


def test_hgb_gives_probabilities(prep):
    y = P.rows_of(prep, prep.y_truth, prep.train_rows)
    ok = ~np.isnan(y)
    m = fit.fit_hgb(prep.fs.X.iloc[prep.train_rows[ok]], y[ok])
    p = fit.predict_hgb(m, prep.fs.X.iloc[prep.test_rows])
    assert p.min() >= 0 and p.max() <= 1 and p.std() > 0


def test_mlp_trains_and_predicts(prep):
    pytest.importorskip("torch")
    y = P.rows_of(prep, prep.y_truth, prep.train_rows)
    ok = ~np.isnan(y)
    m = fit.MlpModel(epochs=1).fit(prep.fs.X.iloc[prep.train_rows[ok]], y[ok])
    p = m.predict(prep.fs.X.iloc[prep.test_rows])
    assert p.shape == (len(prep.test_rows),) and p.min() >= 0 and p.max() <= 1


def test_topk_flags_pick_k_per_site_week(prep):
    scores = np.random.default_rng(0).random(len(prep.test_rows))
    site, week = prep.fs.site[prep.test_rows], prep.fs.week[prep.test_rows]
    sel = P.topk_flags(scores, site, week, 5)
    counts = np.bincount(site[sel] * 1000 + week[sel])
    assert counts[counts > 0].max() == 5
