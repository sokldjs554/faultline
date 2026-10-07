"""정적 데모 빌드 — 콘솔이 쓰는 API 응답을 JSON 파일로 구워 GitHub Pages 에서 백엔드 없이 동작하게 한다.

    python scripts/build_static_demo.py --out docs/demo
콘솔 app.js 의 api() 가 `api/<slug(path)>.json` 을 읽는다 (slug: 앞의 / 제거, / → _). 같은 FastAPI 앱에서 TestClient 로 받아 굽기 때문에
라이브와 정적 데모의 응답이 다를 수 없다. `scripts/smoke_console.cjs` 가 정적 데모에서 404 가 하나라도 나면 실패시킨다.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def slug(path: str) -> str:
    return path.lstrip("/").replace("/", "_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("docs/demo"))
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    a = ap.parse_args()
    from fastapi.testclient import TestClient

    from faultline.api import main as api
    from faultline.api.store import Store

    api.store = Store(a.artifacts)
    if a.out.exists():
        shutil.rmtree(a.out)
    out_api = a.out / "api"
    out_api.mkdir(parents=True)
    n = 0

    def save(path: str):
        nonlocal n
        r = client.get(path)
        r.raise_for_status()
        (out_api / f"{slug(path)}.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, separators=(",", ":"))
        )
        n += 1
        return r.json()

    with TestClient(api.app) as client:
        save("/version")
        save("/v1/schema")
        save("/v1/definitions")
        for name in ("same-log", "ranking", "audit", "monitor"):
            save(f"/v1/screens/{name}")
        save("/v1/quality/sample")
        save("/v1/quality/sample-with-code-book")

    cdir = Path(api.CONSOLE)
    for f in ("style.css", "charts.js", "app.js"):
        shutil.copy(cdir / f, a.out / f)
    html = (cdir / "index.html").read_text()
    html = html.replace(
        '<script src="charts.js"></script>',
        '<script>window.FAULTLINE_STATIC = true;</script>\n<script src="charts.js"></script>',
    )
    html = html.replace("<title>faultline 콘솔</title>", "<title>faultline — 정적 데모</title>")
    (a.out / "index.html").write_text(html)
    (a.out / ".nojekyll").write_text("")
    (a.out / "README.md").write_text(
        "# faultline 정적 데모\n\n`scripts/build_static_demo.py` 가 산출물(artifacts/)을 API 응답 JSON(`api/`)으로 구운 것이다. 모든 데이터는 합성이다.\n"
    )
    total = sum(f.stat().st_size for f in a.out.rglob("*") if f.is_file())
    print(f"[demo] wrote {n} api files to {a.out} ({total / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
