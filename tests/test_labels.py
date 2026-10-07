import numpy as np
import pandas as pd

from faultline.eval.labels import event_week_matrix, match_incidents, window_labels

ASSETS = pd.DataFrame({"asset": [10, 20], "site": [0, 0]})


def ev(rows):
    return pd.DataFrame(rows, columns=["asset", "day"])


def test_matching_is_one_to_one_and_within_tolerance():
    failures = ev([(10, 100), (10, 110), (20, 50)])
    incidents = ev([(10, 103), (10, 200), (20, 70)])
    m = match_incidents(incidents, failures, tol_days=14)
    assert m["matched"] == 1
    assert m["precision"] == 1 / 3 and m["recall"] == 1 / 3
    assert m["timing_median"] == 3


def test_closest_pair_wins():
    failures = ev([(10, 100), (10, 112)])
    incidents = ev([(10, 105), (10, 111)])
    m = match_incidents(incidents, failures, tol_days=14)
    # 가까운 쌍부터 짝짓는다: (111, 112) 오차 -1 다음 (105, 100) 오차 5. 105 를 112 에 먼저 붙이지 않는다
    assert m["matched"] == 2 and m["timing_median"] == 2.0


def test_empty_inputs_do_not_crash():
    m = match_incidents(ev([]), ev([(10, 5)]))
    assert m["recall"] == 0 and np.isnan(m["precision"]) and m["f1"] == 0


def test_window_labels_look_four_weeks_ahead_and_end_with_nan():
    events = ev([(10, 7 * 10 + 2)])  # 10주 차
    y = window_labels(events, ASSETS, n_weeks=20, horizon_weeks=4)
    assert y.shape == (2, 20)
    # t 주를 마친 시점에서 t+1 ~ t+4 주에 사건이 있으면 1: t = 6, 7, 8, 9
    assert list(np.flatnonzero(y[0] == 1)) == [6, 7, 8, 9]
    assert (y[1][:16] == 0).all() and np.isnan(y[:, 16:]).all()


def test_event_week_matrix_ignores_unknown_assets_and_late_days():
    m = event_week_matrix(ev([(10, 0), (10, 3), (99, 10), (20, 7 * 50)]), ASSETS, 20)
    assert m[0, 0] == 2 and m.sum() == 2
