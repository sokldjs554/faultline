"""CSV 로 받은 고객 로그를 읽어 정의 엔진이 쓰는 표로 맞춘다."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from faultline.define.engine import SYMPTOMS
from faultline.quality.contract import KINDS, day_origin, normalize_wo, to_days
from faultline.sim.world import CAT_BY_KEY

ASSET_COLUMNS = ("asset", "site", "category", "floor")
COMPLAINT_COLUMNS = ("site", "floor", "day", "symptom")


@dataclass
class Logs:
    wo_norm: pd.DataFrame
    complaints: pd.DataFrame
    assets: pd.DataFrame
    n_weeks: int


def load_code_book(path: str | Path | None) -> dict[str, str] | None:
    if not path:
        return None
    book = json.loads(Path(path).read_text(encoding="utf-8"))
    bad = {k: v for k, v in book.items() if v not in KINDS}
    if bad:
        raise ValueError(f"코드표의 유형은 {list(KINDS)} 중 하나여야 한다: {bad}")
    return book


def _need(df: pd.DataFrame, cols: tuple[str, ...], what: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise ValueError(f"{what} 표에 필요한 열이 없다: {missing}")


def read_logs(
    work_orders: str | Path,
    assets: str | Path,
    complaints: str | Path | None = None,
    code_book: str | Path | None = None,
    weeks: int | None = None,
) -> Logs:
    """작업지시, 설비 대장, 민원(선택) CSV 를 읽는다. 날짜 열은 가장 이른 작업지시 생성일을 0 으로 하는 일 수로 바꾼다.

    weeks 를 주지 않으면 마지막 기록의 날짜로 관측 기간을 정한다. 마지막 몇 주는 입력이 늦어 기록이 덜 채워졌을 수 있으므로,
    관측이 끝난 시점을 아는 경우에는 weeks 로 직접 준다.
    """
    wo = pd.read_csv(work_orders)
    t0 = day_origin(wo)
    wo = wo.copy()
    wo["created_day"] = to_days(wo["created_day"], t0)
    wo["closed_day"] = to_days(wo["closed_day"], t0)
    book = load_code_book(code_book)
    parts = [normalize_wo(g, book) for _, g in wo.groupby("site")]
    wo_norm = pd.concat(parts, ignore_index=True)
    a = pd.read_csv(assets)
    _need(a, ASSET_COLUMNS, "설비")
    unknown = sorted(set(a["category"]) - set(CAT_BY_KEY))
    if unknown:
        raise ValueError(f"알 수 없는 설비 종류: {unknown}. 사용할 수 있는 종류: {sorted(CAT_BY_KEY)}")
    if complaints:
        c = pd.read_csv(complaints)
        _need(c, COMPLAINT_COLUMNS, "민원")
        c["day"] = to_days(c["day"], t0)
        if "hint_asset" not in c.columns:
            c["hint_asset"] = np.nan
        bad = sorted(set(c["symptom"]) - set(SYMPTOMS))
        if bad:
            raise ValueError(f"알 수 없는 민원 증상: {bad}. 사용할 수 있는 증상: {SYMPTOMS}")
    else:
        c = pd.DataFrame(columns=["site", "floor", "day", "symptom", "hint_asset"])
    last = max(int(wo["created_day"].max()), int(c["day"].max()) if len(c) else 0)
    return Logs(wo_norm, c, a, weeks if weeks else last // 7 + 1)
