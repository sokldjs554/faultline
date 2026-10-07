import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from faultline.api import demo
from faultline.api import main as api
from faultline.api.store import Store
from faultline.define import spec

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def client(prep, monkeypatch):
    monkeypatch.setattr(demo, "prepared", lambda: prep)
    monkeypatch.setattr(api, "store", Store(ROOT / "artifacts"))
    with TestClient(api.app) as c:
        yield c


def test_health_version_metrics(client):
    assert client.get("/health").json() == {"ok": True}
    v = client.get("/version").json()
    assert v["version"] and v["summary"]["auc"]["d1"] < v["summary"]["auc"]["d2"]
    assert "faultline_requests" in client.get("/metrics").text


def test_definitions_listing(client):
    d = client.get("/v1/definitions").json()
    assert len(d["definitions"]) == 6
    assert spec.load_text(d["template"]).name == "d3_corroborated"
    assert all(spec.load_text(x["yaml"]).name == x["name"] for x in d["definitions"])


def test_validate_definition(client):
    ok = client.post("/v1/definitions/validate", json={"yaml": spec.builtin_text("d1_emergency")})
    assert ok.status_code == 200 and ok.json()["definition"]["wo"]["kinds"] == ["emergency"]
    bad = client.post("/v1/definitions/validate", json={"yaml": "name: x\nwo:\n  kinds: [preventive]\n"})
    assert bad.status_code == 422 and "wo.kinds" in bad.json()["detail"]
    assert client.post("/v1/definitions/validate", json={"yaml": "a: [1"}).status_code == 422
    assert client.post("/v1/definitions/validate", json={"yaml": "x" * 9000}).status_code == 422


def test_evaluate_definition_on_demo_world(client):
    r = client.post("/v1/definitions/evaluate", json={"yaml": spec.builtin_text("d2_corrective")})
    assert r.status_code == 200
    j = r.json()
    assert j["overall"]["recall"] > j["overall"]["precision"]
    assert set(j["by_archetype"]) == {
        "표준",
        "긴급 안 씀",
        "긴급 남용",
        "입력 누락",
        "늦게 입력",
        "코드 다름",
    }
    assert 0 < j["window"]["recall"] <= 1 and "model" not in j


def test_evaluate_with_training(client):
    r = client.post(
        "/v1/definitions/evaluate", json={"yaml": spec.builtin_text("d1_emergency"), "train": True}
    )
    m = r.json()["model"]
    assert 0.5 < m["truth_auc"] < 1 and set(m["reference_truth_auc"]) == {"d1_emergency", "d2_corrective"}


def test_quality_upload_roundtrip(client):
    csv = client.get("/v1/sample/work_orders.csv").content
    r = client.post("/v1/quality", files={"file": ("wo.csv", csv, "text/csv")})
    assert r.status_code == 200
    rep = r.json()
    assert {s["site"] for s in rep["sites"]} == set(demo.SAMPLE_SITES)
    assert rep["total"]["unknown_type"] > 0  # 사이트 5 는 코드표가 필요하다
    book = '{"A1": "emergency", "B2": "corrective", "C3": "preventive"}'
    r2 = client.post("/v1/quality", files={"file": ("wo.csv", csv, "text/csv")}, data={"code_book": book})
    assert r2.json()["total"]["unknown_type"] == 0


def test_quality_upload_errors(client):
    csv = client.get("/v1/sample/work_orders.csv").content
    f = {"file": ("wo.csv", csv, "text/csv")}
    assert client.post("/v1/quality", files=f, data={"code_book": "{oops"}).status_code == 400
    assert client.post("/v1/quality", files=f, data={"code_book": '{"A1": "urgent"}'}).status_code == 422
    assert (
        client.post("/v1/quality", files={"file": ("e.csv", io.BytesIO(b""), "text/csv")}).status_code == 400
    )
    no_col = b"wo_id,site\n1,0\n"
    r = client.post("/v1/quality", files={"file": ("x.csv", no_col, "text/csv")})
    assert r.status_code == 422 and "필요한 열" in r.json()["detail"]


def test_sample_tables_are_clean_csv(client):
    text = client.get("/v1/sample/work_orders.csv").text.splitlines()
    assert text[0] == "wo_id,site,asset,created_day,closed_day,type_raw"
    assert ".0," not in text[1]
    for name in ("complaints", "assets"):
        assert client.get(f"/v1/sample/{name}.csv").status_code == 200


def test_screens_and_artifacts(client):
    for name in ("same-log", "ranking", "audit", "monitor"):
        assert client.get(f"/v1/screens/{name}").status_code == 200
    assert client.get("/v1/screens/nope").status_code == 404
    assert client.get("/v1/artifacts/summary").status_code == 200
    assert client.get("/v1/artifacts/not-there").status_code == 404
    assert client.get("/v1/schema").json()["kinds"][0] == "emergency"


def test_console_is_served(client):
    r = client.get("/console/")
    assert r.status_code == 200 and "faultline" in r.text
    assert client.get("/console/app.js").status_code == 200
