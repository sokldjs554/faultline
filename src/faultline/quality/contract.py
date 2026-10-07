"""데이터 계약과 품질 점검.

고객사마다 작업지시 유형 코드가 다르다("긴급", "URGENT", "E", "A1"). 정의 엔진이 읽을 수 있게
유형을 네 가지(긴급, 시정, 예방, 분류 불가)로 정규화하고, 로그의 품질 문제를 사이트별로 센다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

KINDS = ("emergency", "corrective", "preventive", "unknown")
KIND_KO = {"emergency": "긴급", "corrective": "시정", "preventive": "예방", "unknown": "분류 불가"}

LEXICON: dict[str, set[str]] = {
    "emergency": {"긴급", "긴급출동", "응급", "URGENT", "E", "EMG", "EMERGENCY"},
    "preventive": {"예방", "정기", "정기점검", "PM", "P", "PREVENTIVE"},
    "corrective": {"일반", "수리", "보수", "N", "NORMAL", "CM", "CORRECTIVE"},
}
_LOOKUP = {code: kind for kind, codes in LEXICON.items() for code in codes}
REQUIRED_WO_COLUMNS = ("wo_id", "site", "asset", "created_day", "closed_day", "type_raw")


def clean_code(x) -> str:
    return "" if pd.isna(x) else str(x).strip().upper()


def require_columns(wo: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_WO_COLUMNS if c not in wo.columns]
    if missing:
        raise ValueError(f"작업지시 표에 필요한 열이 없다: {missing}")


def normalize_wo(wo: pd.DataFrame, code_book: dict[str, str] | None = None) -> pd.DataFrame:
    """작업지시 유형을 정규화해 `wo_kind` 열을 붙인다. 코드표는 사이트가 쓰는 코드를 직접 지정한다."""
    require_columns(wo)
    book = {clean_code(k): v for k, v in (code_book or {}).items()}
    bad = [v for v in book.values() if v not in KINDS]
    if bad:
        raise ValueError(f"코드표의 유형은 {KINDS} 중 하나여야 한다: {bad}")
    out = wo.copy()
    codes = out["type_raw"].map(clean_code)
    out["wo_kind"] = codes.map(lambda c: book.get(c, _LOOKUP.get(c, "unknown")))
    return out


def suggest_code_book(wo: pd.DataFrame, site: int | None = None) -> dict[str, dict]:
    """분류되지 않은 코드에 유형을 제안한다. 빈도가 가장 높은 코드를 예방, 그다음을 시정, 가장 드문 것을 긴급으로 본다.

    예방 점검이 작업지시의 대부분을 차지하는 로그를 가정한 거친 규칙이라 제안일 뿐이고 사람이 확인해야 한다.
    """
    w = wo if site is None else wo[wo["site"] == site]
    codes = w["type_raw"].map(clean_code)
    unknown = codes[~codes.isin(_LOOKUP)]
    if unknown.empty:
        return {}
    freq = unknown.value_counts()
    order = list(freq.index)
    guess = ["preventive", "corrective", "emergency"]
    out = {}
    for i, code in enumerate(order[:3]):
        out[code] = {
            "kind": guess[i],
            "count": int(freq[code]),
            "confidence": "낮음" if len(order) != 3 else "보통",
        }
    return out


def quality_report(
    wo: pd.DataFrame,
    complaints: pd.DataFrame | None = None,
    assets: pd.DataFrame | None = None,
    code_book_by_site: dict[int, dict[str, str]] | None = None,
    weeks: int | None = None,
) -> dict:
    """사이트별 품질 문제를 센다. 문제 개수와 '정의 엔진이 쓸 수 있는 작업지시 비율'을 돌려준다."""
    rows = []
    issues = []
    books = code_book_by_site or {}
    for site, w in wo.groupby("site"):
        norm = normalize_wo(w, books.get(int(site)))
        n = len(norm)
        exact_dup = int(norm.duplicated(subset=["wo_id", "asset", "created_day", "type_raw"]).sum())
        uniq = norm.drop_duplicates(subset=["wo_id", "asset", "created_day", "type_raw"])
        inverted = int((uniq["closed_day"] < uniq["created_day"]).sum())
        miss_asset = int(uniq["asset"].isna().sum())
        unk = int((uniq["wo_kind"] == "unknown").sum())
        usable = uniq[uniq["asset"].notna() & (uniq["wo_kind"] != "unknown")]
        n_u = max(len(uniq), 1)
        corrective = uniq[uniq["wo_kind"].isin(["emergency", "corrective"])]
        n_assets = int((assets["site"] == site).sum()) if assets is not None else None
        yrs = (weeks / 52) if weeks else None
        rate = (len(corrective) / n_assets / yrs) if (n_assets and yrs) else None
        row = {
            "site": int(site),
            "work_orders": int(n),
            "exact_duplicates": exact_dup,
            "date_inverted": inverted,
            "missing_asset": miss_asset,
            "unknown_type": unk,
            "emergency_share": float((uniq["wo_kind"] == "emergency").sum() / max(len(corrective), 1)),
            "corrective_per_asset_year": rate,
            "usable_share": float(len(usable) / n_u),
        }
        rows.append(row)
        if unk / n_u > 0.05:
            sug = suggest_code_book(w)
            issues.append(
                {
                    "site": int(site),
                    "level": "high",
                    "text": f"작업지시의 {unk / n_u:.0%}가 유형 코드를 분류하지 못함. 코드표가 필요함",
                    "suggestion": sug,
                }
            )
        if miss_asset / n_u > 0.03:
            issues.append(
                {
                    "site": int(site),
                    "level": "mid",
                    "text": f"설비 번호가 빈 작업지시 {miss_asset / n_u:.1%}. 이 기록은 정의에 쓸 수 없음",
                }
            )
        if exact_dup / max(n, 1) > 0.005:
            issues.append(
                {
                    "site": int(site),
                    "level": "low",
                    "text": f"완전히 같은 행 {exact_dup}개. 병합 전에 제거해야 함",
                }
            )
        if inverted / n_u > 0.003:
            issues.append(
                {"site": int(site), "level": "low", "text": f"종료일이 생성일보다 앞선 행 {inverted}개"}
            )
    # 사이트 간 비교: 긴급 유형을 쓰는 정도가 다른 사이트와 크게 다르면 긴급 작업지시를 고장으로 보는 정의를 믿기 어렵다
    shares = [r["emergency_share"] for r in rows]
    med = float(np.median(shares)) if shares else 0.0
    if len(rows) >= 4 and med > 0:
        for r in rows:
            x = r["emergency_share"]
            if r["unknown_type"] / max(r["work_orders"], 1) > 0.05:
                continue  # 코드를 읽지 못한 사이트는 긴급 비중을 말할 수 없다
            if x < 0.25 * med:
                issues.append(
                    {
                        "site": r["site"],
                        "level": "high",
                        "text": f"긴급 유형이 시정·긴급 작업지시의 {x:.0%}뿐임(사이트 중앙값 {med:.0%}). 긴급만 고장으로 보는 정의는 이 사이트의 고장을 대부분 놓침",
                    }
                )
            elif x > 1.8 * med:
                issues.append(
                    {
                        "site": r["site"],
                        "level": "mid",
                        "text": f"긴급 유형이 {x:.0%}로 사이트 중앙값 {med:.0%}의 1.8배를 넘음. 경미한 작업까지 긴급으로 입력했을 수 있고, 긴급만 고장으로 보면 오탐이 많음",
                    }
                )
    issues.sort(key=lambda i: ("high", "mid", "low").index(i["level"]))
    df = pd.DataFrame(rows)
    out = {
        "sites": df.to_dict("records"),
        "total": {
            "work_orders": int(df["work_orders"].sum()),
            "exact_duplicates": int(df["exact_duplicates"].sum()),
            "date_inverted": int(df["date_inverted"].sum()),
            "missing_asset": int(df["missing_asset"].sum()),
            "unknown_type": int(df["unknown_type"].sum()),
            "usable_share_mean": float(df["usable_share"].mean()),
        },
        "issues": issues,
    }
    if complaints is not None and len(complaints):
        out["complaints"] = {
            "rows": int(len(complaints)),
            "missing_floor": int(complaints["floor"].isna().sum()),
            "hint_share": float(complaints["hint_asset"].notna().mean())
            if "hint_asset" in complaints
            else 0.0,
        }
    return out


def flatline_runs(values: np.ndarray, min_len: int = 24) -> list[tuple[int, int]]:
    """계량 값이 같은 값으로 길게 이어진 구간(센서 멈춤 의심)을 찾는다. 실제 계량 데이터에 쓰는 검사."""
    v = np.asarray(values, dtype=float)
    runs, start = [], 0
    for i in range(1, len(v) + 1):
        if i == len(v) or not (v[i] == v[start] or (np.isnan(v[i]) and np.isnan(v[start]))):
            if i - start >= min_len:
                runs.append((start, i))
            start = i
    return runs


def day_origin(wo: pd.DataFrame) -> pd.Timestamp | None:
    """생성일이 날짜 문자열이면 가장 이른 날짜, 이미 숫자면 None."""
    require_columns(wo)
    if pd.api.types.is_numeric_dtype(wo["created_day"]):
        return None
    created = pd.to_datetime(wo["created_day"], errors="coerce")
    if created.isna().all():
        raise ValueError("created_day 를 숫자나 날짜로 읽을 수 없다")
    return created.min()


def to_days(col: pd.Series, t0: pd.Timestamp | None) -> pd.Series:
    """날짜 열을 t0 를 0 으로 하는 일 수로 바꾼다. t0 가 None 이거나 이미 숫자면 그대로 둔다."""
    if t0 is None or pd.api.types.is_numeric_dtype(col):
        return col
    return (pd.to_datetime(col, errors="coerce") - t0).dt.days


def coerce_days(wo: pd.DataFrame) -> pd.DataFrame:
    """생성일·종료일이 날짜 문자열이면 가장 이른 생성일을 0 으로 하는 일 수로 바꾼다. 이미 숫자면 그대로 둔다."""
    t0 = day_origin(wo)
    out = wo.copy()
    if t0 is None:
        return out
    out["created_day"] = to_days(out["created_day"], t0)
    out["closed_day"] = to_days(out["closed_day"], t0)
    return out
