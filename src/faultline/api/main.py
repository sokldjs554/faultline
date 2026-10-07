"""FastAPI. 산출물 조회, 고장 정의 검증·평가, 작업지시 로그 품질 점검.

조회 엔드포인트는 미리 계산한 산출물을 돌려주고, 정의 평가와 품질 점검은 요청마다 계산한다.
정적 데모(GitHub Pages)는 조회 응답을 JSON 으로 구워 둔 것이다.
"""

from __future__ import annotations

import io
import json
import time
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from faultline import __version__
from faultline.api import demo
from faultline.api.store import NAMES, Store
from faultline.define import spec
from faultline.quality.contract import KINDS, coerce_days, quality_report

MAX_ROWS = 400_000
MAX_YAML = 8_000
CONSOLE = Path(__file__).resolve().parent.parent / "console"
SCREENS = ("same-log", "ranking", "audit", "monitor")

app = FastAPI(
    title="faultline",
    version=__version__,
    description="고장을 어떻게 정의하느냐에 따라 예지보전 모형이 달라진다. 정의를 파일로 쓰고, 정답을 아는 합성 세계에서 라벨 품질을 잰다. 모든 데이터는 합성이다.",
)
store = Store()
_metrics = {"requests": 0, "evaluate_calls": 0, "evaluate_seconds": 0.0, "quality_calls": 0}


@app.middleware("http")
async def count(request, call_next):
    _metrics["requests"] += 1
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/version")
def version():
    return {"version": __version__, "manifest": store.artifact("manifest"), "summary": store.artifact("summary")}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics():
    return "\n".join(f"faultline_{k} {v}" for k, v in _metrics.items()) + "\n"


@app.get("/v1/artifacts/{name}")
def artifact(name: str):
    d = store.artifact(name) if name in NAMES else None
    if d is None:
        raise HTTPException(404, f"그런 산출물이 없다: {name}")
    return d


@app.get("/v1/screens/{name}")
def screen(name: str):
    d = store.screen(name) if name in SCREENS else None
    if d is None:
        raise HTTPException(404, f"그런 화면이 없다: {name}")
    return d


# ------------------------------------------------------------------ 고장 정의
@app.get("/v1/definitions")
def definitions():
    out = []
    for name, d in spec.builtin().items():
        out.append({"name": name, "version": d.version, "description": d.description, "spec": d.to_dict(), "yaml": spec.builtin_text(name)})
    return {"definitions": out, "template": spec.builtin_text("d3_corroborated")}


class DefIn(BaseModel):
    yaml: str = Field(..., max_length=MAX_YAML, description="고장 정의 YAML")
    train: bool = Field(False, description="그 라벨로 모형을 학습해 진짜 성능도 잰다(수 초 더 걸린다)")


def _parse(text: str) -> spec.Definition:
    try:
        return spec.load_text(text)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/v1/definitions/validate")
def validate_definition(body: DefIn):
    d = _parse(body.yaml)
    return {"ok": True, "definition": d.to_dict()}


@app.post("/v1/definitions/evaluate")
def evaluate_definition(body: DefIn):
    """정의를 데모 세계(합성, 정답을 안다)에 적용해 라벨 품질을 돌려준다."""
    d = _parse(body.yaml)
    t0 = time.time()
    out = demo.evaluate_definition(d, train=body.train)
    _metrics["evaluate_calls"] += 1
    _metrics["evaluate_seconds"] += time.time() - t0
    return out


# ------------------------------------------------------------------ 로그 품질
def _read_csv(raw: bytes, what: str) -> pd.DataFrame:
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"{what} CSV 를 읽을 수 없다: {e}") from e
    if len(df) > MAX_ROWS:
        raise HTTPException(413, f"{what} 행이 너무 많다 ({len(df):,} > {MAX_ROWS:,})")
    return df


def _book(text: str | None) -> dict[str, str] | None:
    if not text or not text.strip():
        return None
    try:
        book = json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"코드표 JSON 을 읽을 수 없다: {e}") from e
    bad = {k: v for k, v in book.items() if v not in KINDS}
    if bad:
        raise HTTPException(422, f"코드표의 유형은 {list(KINDS)} 중 하나여야 한다: {bad}")
    return book


def _report(wo: pd.DataFrame, cm: pd.DataFrame | None, assets: pd.DataFrame | None, book: dict | None, weeks: int | None) -> dict:
    try:
        wo = coerce_days(wo)
        books = None if book is None else {int(s): book for s in wo["site"].unique()}
        if weeks is None:
            weeks = int(wo["created_day"].max() // 7) + 1
        return quality_report(wo, cm, assets, books, weeks)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@app.post("/v1/quality")
async def quality(
    file: UploadFile = File(..., description="작업지시 CSV: wo_id, site, asset, created_day, closed_day, type_raw"),
    complaints: UploadFile | None = File(None),
    assets: UploadFile | None = File(None),
    code_book: str | None = Form(None, description='{"A1":"emergency"} 처럼 코드를 유형으로 옮기는 JSON'),
):
    """작업지시 로그의 품질 문제를 사이트별로 센다. 올린 데이터는 저장하지 않는다."""
    wo = _read_csv(await file.read(), "작업지시")
    cm = _read_csv(await complaints.read(), "민원") if complaints else None
    a = _read_csv(await assets.read(), "설비") if assets else None
    _metrics["quality_calls"] += 1
    return _report(wo, cm, a, _book(code_book), None)


@app.get("/v1/quality/sample")
def quality_sample():
    t = demo.sample_tables()
    return _report(t["work_orders"], t["complaints"], t["assets"], None, t["weeks"])


@app.get("/v1/quality/sample-with-code-book")
def quality_sample_with_book():
    from faultline.eval.protocol import true_code_book

    t = demo.sample_tables()
    return _report(t["work_orders"], t["complaints"], t["assets"], true_code_book("code"), t["weeks"])


@app.get("/v1/schema")
def schema():
    return {
        "max_rows": MAX_ROWS,
        "work_orders": [
            {"column": "wo_id", "type": "int|str", "meaning": "작업지시 번호"},
            {"column": "site", "type": "int|str", "meaning": "사이트(고객사·건물)"},
            {"column": "asset", "type": "int|str|빈 값", "meaning": "설비 번호. 비면 정의에 쓸 수 없다"},
            {"column": "created_day", "type": "int|날짜", "meaning": "생성일. 날짜면 가장 이른 날을 0 으로 바꾼다"},
            {"column": "closed_day", "type": "int|날짜", "meaning": "종료일"},
            {"column": "type_raw", "type": "str", "meaning": "고객사가 쓰는 유형 코드(긴급, URGENT, E, A1 ...)"},
        ],
        "kinds": list(KINDS),
    }


def _csv(df: pd.DataFrame, name: str) -> Response:
    return Response(df.to_csv(index=False), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={name}"})


@app.get("/v1/sample/work_orders.csv")
def sample_wo():
    return _csv(demo.sample_tables()["work_orders"], "faultline_sample_work_orders.csv")


@app.get("/v1/sample/complaints.csv")
def sample_cm():
    return _csv(demo.sample_tables()["complaints"], "faultline_sample_complaints.csv")


@app.get("/v1/sample/assets.csv")
def sample_assets():
    return _csv(demo.sample_tables()["assets"], "faultline_sample_assets.csv")


if CONSOLE.exists():
    app.mount("/console", StaticFiles(directory=CONSOLE, html=True), name="console")

    @app.get("/")
    def root():
        index = CONSOLE / "index.html"
        return FileResponse(index) if index.exists() else {"service": "faultline", "docs": "/docs"}
