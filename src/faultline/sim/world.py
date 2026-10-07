"""시설관리 로그 시뮬레이터.

설비가 닳아서 진짜 고장이 나고, 사이트마다 다른 습관으로 작업지시·민원·점검 기록이 남는다.
추정기가 보는 것은 기록뿐이고, 진짜 고장은 `World.failures` 에 따로 있다.
고장 정의가 정답을 얼마나 맞히는지 재려면 정답이 필요하기 때문에 시뮬레이터를 쓴다.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Category:
    key: str
    ko: str
    h0: float  # 손상이 1 일 때 주당 고장 위험
    wear: float  # 주당 평균 손상 증가
    detect: float  # 정기 점검에서 결함을 찾을 확률
    central: bool  # 기계실 설비(민원에서 층으로 특정할 수 없다)
    symptoms: tuple[str, ...]
    complaint_factor: float  # 고장 났을 때 사용자가 민원을 낼 가능성에 곱하는 값


CATS: tuple[Category, ...] = (
    Category("ahu", "공조기", 0.0060, 0.0125, 0.70, False, ("냉방불량", "난방불량", "환기불량"), 1.0),
    Category("chiller", "냉동기", 0.0050, 0.0110, 0.75, True, ("냉방불량",), 1.0),
    Category("boiler", "보일러", 0.0050, 0.0110, 0.75, True, ("난방불량", "온수불량"), 1.0),
    Category("pump", "펌프", 0.0070, 0.0140, 0.65, True, ("수압저하", "소음", "누수"), 0.7),
    Category("fire_pump", "소방펌프", 0.0040, 0.0090, 0.55, True, ("소방경보",), 0.25),
    Category("elevator", "승강기", 0.0060, 0.0120, 0.60, False, ("승강기정지", "갇힘"), 1.2),
    Category("generator", "발전기", 0.0040, 0.0100, 0.50, True, ("정전",), 0.6),
    Category("switchgear", "수배전반", 0.0030, 0.0090, 0.40, True, ("정전", "전기불량"), 0.6),
)
CAT_BY_KEY = {c.key: c for c in CATS}
COMFORT_SYMPTOMS = ("냉방불량", "난방불량", "소음", "환기불량", "수압저하")
MINOR_TEXTS = ("소모품 교체", "점검 요청", "경미 불량 확인", "필터 교체", "도색 보수")

# 증상이 가리킬 수 있는 설비 종류
SYMPTOM_CATS: dict[str, tuple[str, ...]] = {}
for _c in CATS:
    for _s in _c.symptoms:
        SYMPTOM_CATS[_s] = (*SYMPTOM_CATS.get(_s, ()), _c.key)

CODE_SCHEMES = {
    "ko": {"emergency": "긴급", "corrective": "일반", "preventive": "예방"},
    "en": {"emergency": "URGENT", "corrective": "NORMAL", "preventive": "PM"},
    "short": {"emergency": "E", "corrective": "N", "preventive": "P"},
    "code": {"emergency": "A1", "corrective": "B2", "preventive": "C3"},
}


@dataclass(frozen=True)
class Habit:
    """사이트가 기록을 남기는 습관."""

    name: str
    p_em_stop: float  # 정지 고장을 '긴급'으로 입력할 확률
    p_em_degraded: float
    p_em_minor: float  # 고장이 아닌 경미 작업을 '긴급'으로 입력할 확률
    report_stop: float  # 고장이 작업지시로 남을 확률
    report_degraded: float
    delay_median: float  # 고장 난 날부터 작업지시 입력까지 중앙값(일)
    dup_rate: float  # 같은 건에 작업지시가 두 번 열리는 비율
    complaint_stop: float
    complaint_degraded: float
    minor_rate: float  # 설비당 주당 고장 아닌 시정 작업지시 수
    missing_asset_rate: float  # 설비 번호가 비는 작업지시 비율
    scheme: str  # 작업지시 유형 코드 체계


ARCHETYPES: dict[str, Habit] = {
    "표준": Habit("표준", 0.90, 0.30, 0.03, 0.97, 0.90, 2.0, 0.05, 0.70, 0.35, 0.010, 0.010, "ko"),
    "긴급 안 씀": Habit("긴급 안 씀", 0.04, 0.02, 0.0, 0.95, 0.88, 3.0, 0.06, 0.65, 0.30, 0.010, 0.020, "en"),
    "긴급 남용": Habit(
        "긴급 남용", 0.97, 0.85, 0.55, 0.97, 0.92, 1.0, 0.05, 0.70, 0.35, 0.020, 0.020, "short"
    ),
    "입력 누락": Habit("입력 누락", 0.88, 0.25, 0.02, 0.55, 0.35, 3.0, 0.05, 0.85, 0.50, 0.008, 0.060, "ko"),
    "늦게 입력": Habit("늦게 입력", 0.90, 0.30, 0.03, 0.95, 0.88, 14.0, 0.08, 0.70, 0.35, 0.010, 0.020, "en"),
    "코드 다름": Habit(
        "코드 다름", 0.90, 0.30, 0.03, 0.97, 0.90, 2.0, 0.05, 0.70, 0.35, 0.010, 0.010, "code"
    ),
}
ARCHETYPE_ORDER = tuple(ARCHETYPES)


@dataclass(frozen=True)
class WorldConfig:
    seed: int = 7
    n_sites: int = 16
    weeks: int = 156  # 기록이 남는 기간
    burn_in: int = 26  # 손상 분포를 안정시키는 기간(기록 없음)
    horizon_days: int = 28  # 예측 창
    target_failures_per_asset_year: float = 0.40
    hazard_scale: float = 1.0  # calibrate() 가 채운다
    beta: float = 4.5  # 손상이 클수록 고장 위험이 오르는 가파름
    minor_gain: float = 3.0  # 손상이 클수록 경미 작업지시가 늘어나는 정도
    pre_cmp_rate: float = 0.05  # 손상이 클수록 약한 민원이 늘어나는 정도
    uniform_habit: bool = False  # 대조군: 모든 사이트가 '표준' 습관
    shifts: tuple[tuple[int, int, str], ...] = ()  # (사이트, 바뀌는 주, 새 습관 이름)
    p_stop: float = 0.6  # 고장 중 정지 비율(나머지는 성능저하)


@dataclass
class World:
    cfg: WorldConfig
    assets: pd.DataFrame
    wo: pd.DataFrame
    complaints: pd.DataFrame
    pm: pd.DataFrame
    failures: pd.DataFrame  # 정답
    wo_truth: pd.DataFrame
    complaint_truth: pd.DataFrame
    sites: pd.DataFrame
    meta: dict = field(default_factory=dict)

    @property
    def days(self) -> int:
        return self.cfg.weeks * 7


def habit_name_for(cfg: WorldConfig, site: int, week: int, base: str) -> str:
    name = base
    for s, w, new in cfg.shifts:
        if s == site and week >= w:
            name = new
    return name


def assign_archetypes(cfg: WorldConfig) -> list[str]:
    if cfg.uniform_habit:
        return ["표준"] * cfg.n_sites
    return [ARCHETYPE_ORDER[i % len(ARCHETYPE_ORDER)] for i in range(cfg.n_sites)]


def _jitter(h: Habit, rng: np.random.Generator, strength: float = 0.12) -> Habit:
    """같은 습관이라도 사이트마다 조금씩 다르다. 확률은 [0, 0.99] 안에 둔다."""

    def p(x):
        if x in (0.0, 1.0):
            return x
        return float(np.clip(x * np.exp(rng.normal(0, strength)), 0.0, 0.99))

    return replace(
        h,
        p_em_stop=p(h.p_em_stop),
        p_em_degraded=p(h.p_em_degraded),
        p_em_minor=p(h.p_em_minor),
        report_stop=p(h.report_stop),
        report_degraded=p(h.report_degraded),
        delay_median=float(max(0.5, h.delay_median * np.exp(rng.normal(0, 2 * strength)))),
        dup_rate=p(h.dup_rate),
        complaint_stop=p(h.complaint_stop),
        complaint_degraded=p(h.complaint_degraded),
        minor_rate=float(h.minor_rate * np.exp(rng.normal(0, strength))),
    )


def _build_assets(rng: np.random.Generator, site: int, floors: int) -> pd.DataFrame:
    rows = []

    def add(cat: str, n: int, floor_fn):
        for _ in range(n):
            rows.append((cat, floor_fn(), float(rng.gamma(4.0, 3.0))))

    for f in range(floors):
        add("ahu", int(rng.integers(3, 6)), lambda f=f: f)
    add("elevator", int(rng.integers(3, 7)), lambda: -1)
    add("chiller", int(rng.integers(1, 4)), lambda: -1)
    add("boiler", int(rng.integers(1, 3)), lambda: -1)
    add("pump", int(rng.integers(8, 17)), lambda: -1)
    add("fire_pump", int(rng.integers(2, 5)), lambda: -1)
    add("generator", int(rng.integers(1, 3)), lambda: -1)
    add("switchgear", int(rng.integers(2, 5)), lambda: -1)
    df = pd.DataFrame(rows, columns=["category", "floor", "age_years"])
    df.insert(0, "site", site)
    return df


def calibrate(cfg: WorldConfig, n_assets: int = 600) -> WorldConfig:
    """고장 위험 배수를 맞춰 설비당 연간 고장 수가 목표에 가깝게 한다."""
    rng = np.random.default_rng(cfg.seed + 991)
    cats = rng.integers(0, len(CATS), n_assets)
    h0 = np.array([c.h0 for c in CATS])[cats]
    wear = np.array([c.wear for c in CATS])[cats]
    scale = 1.0
    for _ in range(4):
        D = rng.uniform(0.1, 1.1, n_assets)
        fails = 0
        weeks = 104
        for _w in range(cfg.burn_in + weeks):
            D += wear * rng.gamma(2.0, 0.5, n_assets)
            p = 1 - np.exp(-scale * h0 * np.exp(cfg.beta * (D - 1.0)))
            f = rng.random(n_assets) < p
            if _w >= cfg.burn_in:
                fails += int(f.sum())
            D[f] = 0.25
            # 정기 점검이 손상을 절반쯤 되돌리는 효과를 거칠게 반영
            D[(_w % 13 == 0) & (D > 0.9)] = 0.45
        rate = fails / n_assets / (weeks / 52)
        scale *= cfg.target_failures_per_asset_year / max(rate, 1e-6)
    return replace(cfg, hazard_scale=float(scale))


def _lognormal_days(rng: np.random.Generator, median: float, size: int | None = None, sigma: float = 0.7):
    x = rng.lognormal(np.log(max(median, 0.3)), sigma, size)
    return np.maximum(0, np.round(x)).astype(int)


def _type_raw(rng: np.random.Generator, scheme: str, kind: str) -> str:
    code = CODE_SCHEMES[scheme][kind]
    u = rng.random()
    if u < 0.02:
        return code + " "  # 끝 공백
    if u < 0.04:
        return code.lower() if code.isascii() else code
    return code


def simulate(cfg: WorldConfig) -> World:
    """세계를 만든다. cfg.hazard_scale 이 1.0 이면 먼저 calibrate() 한다."""
    if cfg.hazard_scale == 1.0:
        cfg = calibrate(cfg)
    archs = assign_archetypes(cfg)
    n_weeks = cfg.weeks
    assets_all, wo_rows, cmp_rows, pm_rows, fail_rows, wo_truth, cmp_truth, site_rows = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    wo_id = cmp_id = fail_id = pm_id = 0
    asset_offset = 0
    dmg_all = []

    for s in range(cfg.n_sites):
        rng = np.random.default_rng([cfg.seed, s])
        floors = int(rng.integers(5, 11))
        assets = _build_assets(rng, s, floors)
        n = len(assets)
        assets.insert(0, "asset", np.arange(asset_offset, asset_offset + n))
        asset_offset += n
        base_habit = _jitter(ARCHETYPES[archs[s]], rng)
        habit_cache: dict[str, Habit] = {archs[s]: base_habit}

        def habit_at(week: int, s=s, base=archs[s], habit_cache=habit_cache, rng=rng) -> Habit:
            nm = habit_name_for(cfg, s, week, base)
            if nm not in habit_cache:
                habit_cache[nm] = _jitter(ARCHETYPES[nm], rng)
            return habit_cache[nm]

        cat_idx = assets["category"].map({c.key: i for i, c in enumerate(CATS)}).to_numpy()
        h0 = np.array([c.h0 for c in CATS])[cat_idx]
        wear = np.array([c.wear for c in CATS])[cat_idx]
        det = np.array([c.detect for c in CATS])[cat_idx]
        cmp_factor = np.array([c.complaint_factor for c in CATS])[cat_idx]
        pm_period = int(rng.choice([8, 13, 13, 26]))
        pm_offset = rng.integers(0, pm_period, n)
        D = np.clip(rng.uniform(0.1, 1.1, n) + 0.01 * assets["age_years"].to_numpy(), 0.05, 1.6)

        events = []  # (week, asset_idx, kind, extra)
        dmg = np.zeros((n, n_weeks), dtype=np.float32)
        for w in range(cfg.burn_in + n_weeks):
            t = w - cfg.burn_in
            D += wear * rng.gamma(2.0, 0.5, n)
            if t >= 0:
                dmg[:, t] = D
                h_t = habit_at(t)
                p_minor = np.clip(
                    h_t.minor_rate * (0.35 + cfg.minor_gain * np.clip(D - 0.5, 0, 1.2)), 0, 0.25
                )
                for i in np.flatnonzero(rng.random(n) < p_minor):
                    events.append((t, int(i), "minor", None))
                p_pre = cfg.pre_cmp_rate * np.clip(D - 0.7, 0, 1.0) * cmp_factor
                for i in np.flatnonzero(rng.random(n) < p_pre):
                    events.append((t, int(i), "pre_cmp", None))
            p = 1 - np.exp(-cfg.hazard_scale * h0 * np.exp(cfg.beta * (D - 1.0)))
            fail = rng.random(n) < p
            fidx = np.flatnonzero(fail)
            if t >= 0:
                for i in fidx:
                    sev = "stop" if rng.random() < cfg.p_stop else "degraded"
                    events.append((t, int(i), "failure", sev))
            D[fidx] = 0.25 + rng.uniform(0, 0.1, len(fidx))
            due = ((w + pm_offset) % pm_period == 0) & ~fail
            didx = np.flatnonzero(due)
            if len(didx):
                eps = rng.normal(0, 0.15, len(didx))
                score = D[didx] + eps
                grade = np.where(score < 0.8, 0, np.where(score < 1.2, 1, 2))
                found = (grade >= 1) & (rng.random(len(didx)) < det[didx] * np.where(grade == 2, 1.0, 0.5))
                if t >= 0:
                    for k, i in enumerate(didx):
                        events.append((t, int(i), "pm", (int(grade[k]), bool(found[k]))))
                D[didx[found]] = 0.4 + rng.uniform(0, 0.1, int(found.sum()))

        site_rows.append(
            {
                "site": s,
                "archetype": archs[s],
                "floors": floors,
                "assets": n,
                "pm_period": pm_period,
                **{f"habit_{k}": v for k, v in base_habit.__dict__.items() if k not in ("name",)},
            }
        )
        assets_all.append(assets)
        dmg_all.append(dmg)
        asset_ids = assets["asset"].to_numpy()
        floors_arr = assets["floor"].to_numpy()
        cats_arr = assets["category"].to_numpy()

        # ---- 기록 만들기
        for t, i, kind, extra in sorted(events, key=lambda e: e[0]):
            h = habit_at(t)
            a = int(asset_ids[i])
            cat = CAT_BY_KEY[cats_arr[i]]
            if kind == "failure":
                sev = extra
                day = t * 7 + int(rng.integers(0, 7))
                fid = fail_id
                fail_id += 1
                fail_rows.append((fid, s, a, day, sev, cats_arr[i]))
                # 작업지시
                p_rep = h.report_stop if sev == "stop" else h.report_degraded
                if rng.random() < p_rep:
                    med = h.delay_median * (0.6 if sev == "stop" else 1.5)
                    created = day + int(_lognormal_days(rng, med))
                    p_em = h.p_em_stop if sev == "stop" else h.p_em_degraded
                    kind_wo = "emergency" if rng.random() < p_em else "corrective"
                    txt = f"{cat.ko} {rng.choice(cat.symptoms)} 조치 요청"
                    n_wo = 2 if rng.random() < h.dup_rate else 1
                    for k in range(n_wo):
                        c_day = created + (0 if k == 0 else int(rng.integers(1, 11)))
                        miss = rng.random() < h.missing_asset_rate
                        wo_rows.append(
                            (
                                wo_id,
                                s,
                                np.nan if miss else a,
                                c_day,
                                c_day + int(rng.integers(1, 15)),
                                _type_raw(rng, h.scheme, kind_wo),
                                txt,
                            )
                        )
                        wo_truth.append(
                            (wo_id, fid if k == 0 else fid, "failure" if k == 0 else "failure_dup")
                        )
                        wo_id += 1
                # 민원
                p_cmp = (h.complaint_stop if sev == "stop" else h.complaint_degraded) * cat.complaint_factor
                if rng.random() < min(p_cmp, 0.97):
                    lam = 1.5 if sev == "stop" else 0.6
                    for _ in range(1 + int(rng.poisson(lam))):
                        sym = str(rng.choice(cat.symptoms))
                        floor = int(floors_arr[i]) if floors_arr[i] >= 0 else int(rng.integers(0, floors))
                        hint = a if (cat.key == "elevator" and rng.random() < 0.8) else None
                        cmp_rows.append(
                            (
                                cmp_id,
                                s,
                                floor,
                                day + int(rng.integers(0, 4)),
                                sym,
                                hint,
                                f"{floor + 1}층 {sym}",
                            )
                        )
                        cmp_truth.append((cmp_id, fid))
                        cmp_id += 1
            elif kind == "minor":  # 고장은 아니지만 손상이 커질수록 늘어나는 경미 작업지시
                day = t * 7 + int(rng.integers(0, 7))
                kind_wo = "emergency" if rng.random() < h.p_em_minor else "corrective"
                miss = rng.random() < h.missing_asset_rate
                wo_rows.append(
                    (
                        wo_id,
                        s,
                        np.nan if miss else a,
                        day,
                        day + int(rng.integers(1, 10)),
                        _type_raw(rng, h.scheme, kind_wo),
                        str(rng.choice(MINOR_TEXTS)),
                    )
                )
                wo_truth.append((wo_id, -1, "minor"))
                wo_id += 1
            elif kind == "pre_cmp":  # 고장 전에 늘어나는 약한 민원
                sym = str(rng.choice(cat.symptoms))
                floor = int(floors_arr[i]) if floors_arr[i] >= 0 else int(rng.integers(0, floors))
                cmp_rows.append(
                    (cmp_id, s, floor, t * 7 + int(rng.integers(0, 7)), sym, None, f"{floor + 1}층 {sym}")
                )
                cmp_truth.append((cmp_id, -1))
                cmp_id += 1
            else:  # 정기 점검
                grade, found = extra
                day = t * 7 + int(rng.integers(0, 7))
                pm_rows.append((pm_id, s, a, day, grade))
                pm_id += 1
                wo_rows.append(
                    (
                        wo_id,
                        s,
                        a,
                        day,
                        day + int(rng.integers(0, 3)),
                        _type_raw(rng, h.scheme, "preventive"),
                        f"{cat.ko} 정기점검",
                    )
                )
                wo_truth.append((wo_id, -1, "preventive"))
                wo_id += 1
                if found:
                    kind_wo = "emergency" if rng.random() < h.p_em_minor else "corrective"
                    c_day = day + int(rng.integers(0, 6))
                    miss = rng.random() < h.missing_asset_rate
                    wo_rows.append(
                        (
                            wo_id,
                            s,
                            np.nan if miss else a,
                            c_day,
                            c_day + int(rng.integers(1, 15)),
                            _type_raw(rng, h.scheme, kind_wo),
                            f"{cat.ko} 점검 후 보수",
                        )
                    )
                    wo_truth.append((wo_id, -1, "pm_repair"))
                    wo_id += 1

        # 배경 민원(냉난방 불만 등): 고장과 무관하게 층마다 일정하게 들어온다
        for t in range(n_weeks):
            for f in range(floors):
                for _ in range(int(rng.poisson(0.08))):
                    sym = str(rng.choice(COMFORT_SYMPTOMS))
                    cmp_rows.append(
                        (cmp_id, s, f, t * 7 + int(rng.integers(0, 7)), sym, None, f"{f + 1}층 {sym}")
                    )
                    cmp_truth.append((cmp_id, -1))
                    cmp_id += 1

    assets_df = pd.concat(assets_all, ignore_index=True)
    assets_df["install_day"] = -(assets_df["age_years"] * 365).astype(int)
    wo = pd.DataFrame(
        wo_rows, columns=["wo_id", "site", "asset", "created_day", "closed_day", "type_raw", "text"]
    )
    complaints = pd.DataFrame(
        cmp_rows, columns=["complaint_id", "site", "floor", "day", "symptom", "hint_asset", "text"]
    )
    pm = pd.DataFrame(pm_rows, columns=["pm_id", "site", "asset", "day", "grade"])
    failures = pd.DataFrame(fail_rows, columns=["failure_id", "site", "asset", "day", "severity", "category"])
    wo_truth_df = pd.DataFrame(wo_truth, columns=["wo_id", "failure_id", "kind"])
    cmp_truth_df = pd.DataFrame(cmp_truth, columns=["complaint_id", "failure_id"])

    # 기록이 지저분해지는 정도: 같은 행이 두 번 들어가거나 종료일이 생성일보다 앞선다
    rng = np.random.default_rng([cfg.seed, 9999])
    bad = rng.random(len(wo)) < 0.005
    wo.loc[bad, "closed_day"] = wo.loc[bad, "created_day"] - rng.integers(1, 5, int(bad.sum()))
    dup_rows = wo.sample(frac=0.01, random_state=cfg.seed)
    wo = (
        pd.concat([wo, dup_rows], ignore_index=True)
        .sort_values(["created_day", "wo_id"], kind="stable")
        .reset_index(drop=True)
    )

    sites = pd.DataFrame(site_rows)
    return World(
        cfg,
        assets_df,
        wo,
        complaints,
        pm,
        failures,
        wo_truth_df,
        cmp_truth_df,
        sites,
        meta={"n_exact_dup_wo": len(dup_rows), "damage": np.concatenate(dmg_all)},
    )
