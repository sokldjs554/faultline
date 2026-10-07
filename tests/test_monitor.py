import numpy as np

from faultline.monitor.drift import binned_counts, cusum, monitor_sites


def test_cusum_is_quiet_on_noise_and_alarms_on_a_step():
    rng = np.random.default_rng(0)
    quiet = rng.normal(0, 1, 60)
    idx, path = cusum(quiet, base_end=15, k=0.5, h=10)
    assert idx is None and len(path) == 60
    step = np.r_[rng.normal(0, 1, 30), rng.normal(2, 1, 30)]
    idx, _ = cusum(step, base_end=15, k=0.5, h=10)
    assert idx is not None and 30 <= idx <= 40


def test_cusum_catches_a_drop_too():
    z = np.r_[np.zeros(20), np.full(20, -2.0)]
    idx, _ = cusum(z, base_end=10, k=0.5, h=5)
    assert idx is not None and idx >= 20


def test_binned_counts_cover_every_site(prep):
    w = prep.world
    counts = binned_counts(prep.wo_norm, w.assets, w.cfg.weeks, 4, w.complaints)
    assert set(counts) == set(w.sites["site"])
    c0 = counts[0]
    assert len(c0) == w.cfg.weeks // 4
    assert (c0["np"] <= c0["tot"]).all() and (c0["lk"] <= c0["cm"]).all()


def test_monitor_quiet_world_has_few_alarms(prep):
    w = prep.world
    res = monitor_sites(prep.wo_norm, w.assets, w.cfg.weeks, w.complaints, h=10.0)
    alarms = [v["alarm_week"] for v in res["sites"].values() if v["alarm_week"] is not None]
    assert len(alarms) <= 2
    s0 = res["sites"][0]
    assert set(s0["signals"]) == {"np_rate", "em_share", "unknown_share", "missing_share", "link_share"}
    assert len(s0["weeks"]) == len(s0["series"]["em_share"])
