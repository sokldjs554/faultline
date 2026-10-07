import numpy as np

from faultline.quality.contract import normalize_wo
from faultline.sim.world import ARCHETYPE_ORDER, WorldConfig, simulate


def test_same_seed_same_world():
    a = simulate(WorldConfig(seed=5, n_sites=2))
    b = simulate(WorldConfig(seed=5, n_sites=2))
    assert a.wo.equals(b.wo) and a.failures.equals(b.failures) and a.complaints.equals(b.complaints)


def test_other_seed_differs():
    a = simulate(WorldConfig(seed=5, n_sites=2))
    b = simulate(WorldConfig(seed=6, n_sites=2))
    assert not a.failures.equals(b.failures)


def test_archetypes_cycle(world):
    assert list(world.sites["archetype"]) == list(ARCHETYPE_ORDER)


def test_failure_rate_is_plausible(world):
    years = world.cfg.weeks / 52
    rate = len(world.failures) / len(world.assets) / years
    assert 0.3 < rate < 1.0


def test_days_are_inside_the_record_window(world):
    end = world.cfg.weeks * 7
    for df, col in (
        (world.wo, "created_day"),
        (world.complaints, "day"),
        (world.failures, "day"),
        (world.pm, "day"),
    ):
        assert df[col].min() >= 0 and df[col].max() < end + 60


def test_truth_tables_point_at_real_rows(world):
    assert set(world.wo_truth["wo_id"]) <= set(world.wo["wo_id"])
    ids = set(world.failures["failure_id"]) | {-1}
    assert set(world.wo_truth["failure_id"]) <= ids
    assert set(world.complaint_truth["failure_id"]) <= ids
    assert set(world.complaint_truth["complaint_id"]) == set(world.complaints["complaint_id"])


def test_dirty_rows_exist_and_are_counted(world):
    wo = world.wo
    dup = int(wo.duplicated(subset=["wo_id", "asset", "created_day", "type_raw"]).sum())
    assert dup > 0
    assert dup >= world.meta["n_exact_dup_wo"]
    assert (wo["closed_day"] < wo["created_day"]).any()
    assert wo["asset"].isna().any()


def test_code_schemes_follow_site_habit(world):
    """유형 코드는 사이트 체계를 따르고, 공백과 대소문자 변형이 섞여 있다."""
    clean = world.wo.assign(c=world.wo["type_raw"].str.strip().str.upper()).groupby("site")["c"].agg(set)
    sites = world.sites.set_index("site")
    code_site = sites.index[sites["habit_scheme"] == "code"][0]
    assert clean[code_site] <= {"A1", "B2", "C3"}
    ko_site = sites.index[sites["habit_scheme"] == "ko"][0]
    assert clean[ko_site] >= {"긴급", "예방"}
    assert (world.wo["type_raw"] != world.wo["type_raw"].str.strip()).any()


def test_habit_shows_in_records(world):
    sites = world.sites.set_index("site")["archetype"]
    f = world.wo_truth[world.wo_truth["kind"] == "failure"].merge(
        world.wo[["wo_id", "site", "type_raw"]].drop_duplicates("wo_id"), on="wo_id"
    )
    f["arch"] = f["site"].map(sites)
    emergency = {"긴급", "URGENT", "E", "A1"}
    share = f.assign(e=f["type_raw"].isin(emergency)).groupby("arch")["e"].mean()
    # 코드가 다른 사이트(A1)도 긴급을 쓰므로 비교는 영어·한글 사이트끼리만 의미가 있다
    assert share["긴급 남용"] > share["표준"] > share["긴급 안 씀"]


def test_uniform_world_has_one_habit():
    w = simulate(WorldConfig(seed=2, n_sites=4, uniform_habit=True))
    assert set(w.sites["archetype"]) == {"표준"}


def test_shift_changes_the_log_after_the_shift_week():
    base = simulate(WorldConfig(seed=4, n_sites=1))
    shifted = simulate(WorldConfig(seed=4, n_sites=1, shifts=((0, 100, "긴급 남용"),)))

    def em_share(w, lo, hi):
        wo = normalize_wo(w.wo)
        wo = wo[
            (wo["created_day"] >= lo)
            & (wo["created_day"] < hi)
            & wo["wo_kind"].isin(["emergency", "corrective"])
        ]
        return float((wo["wo_kind"] == "emergency").mean())

    after = (700, 156 * 7)
    assert em_share(shifted, *after) > em_share(base, *after) + 0.2


def test_damage_matrix_shape(world):
    d = world.meta["damage"]
    assert d.shape[0] == len(world.assets)
    assert np.isfinite(d).all() and (d >= 0).all()
