import json
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

from faultline.define import spec
from faultline.eval import audit
from faultline.eval.labels import window_labels
from faultline.logs import read_logs

SITE = 1  # 긴급 안 씀


@pytest.fixture()
def files(world, tmp_path):
    wo = world.wo[["wo_id", "site", "asset", "created_day", "closed_day", "type_raw"]].copy()
    wo["asset"] = wo["asset"].astype("Int64")
    cm = world.complaints[["site", "floor", "day", "symptom", "hint_asset"]].copy()
    cm["hint_asset"] = cm["hint_asset"].astype("Int64")
    paths = {"wo": tmp_path / "wo.csv", "cm": tmp_path / "cm.csv", "assets": tmp_path / "assets.csv"}
    wo.to_csv(paths["wo"], index=False)
    cm.to_csv(paths["cm"], index=False)
    world.assets[["asset", "site", "category", "floor"]].to_csv(paths["assets"], index=False)
    return paths


def truth_for(world, sample):
    y = window_labels(world.failures, world.assets, world.cfg.weeks, 4)
    pos = {a: i for i, a in enumerate(world.assets["asset"])}
    return [int(y[pos[a], w]) for a, w in zip(sample["asset"], sample["week"], strict=True)]


def test_read_logs_and_windows(world, files):
    logs = read_logs(files["wo"], files["assets"], files["cm"], None, weeks=world.cfg.weeks)
    assert logs.n_weeks == world.cfg.weeks
    assert read_logs(files["wo"], files["assets"], files["cm"]).n_weeks >= world.cfg.weeks
    defs = spec.builtin()
    L, index = audit.site_windows(defs, logs.wo_norm, logs.complaints, logs.assets, SITE, logs.n_weeks)
    n_assets = int((world.assets["site"] == SITE).sum())
    assert L.shape == (len(defs), n_assets * (logs.n_weeks - 4)) and len(index) == L.shape[1]
    assert L[1].sum() > L[0].sum()  # d2 는 d1 보다 넓다


def test_sample_and_estimate_roundtrip(world, files):
    logs = read_logs(files["wo"], files["assets"], files["cm"], None, weeks=world.cfg.weeks)
    defs = spec.builtin()
    L, index = audit.site_windows(defs, logs.wo_norm, logs.complaints, logs.assets, SITE, logs.n_weeks)
    plan = audit.plan_sample(defs, L, index, SITE, 300, seed=1)
    assert set(plan["stratum"]) == {"S1", "S0"} and (plan["confirmed"] == "").all()
    assert (plan[plan["stratum"] == "S0"]["flagged_by"] == "").all() and (
        plan[plan["stratum"] == "S1"]["flagged_by"] != ""
    ).all()
    assert (plan["to_day"] - plan["from_day"] == 28).all()
    plan["confirmed"] = truth_for(world, plan)
    res = audit.estimate_from_sample(defs, L, index, plan, boot=50)
    d1, d2 = res["definitions"]["d1_emergency"], res["definitions"]["d2_corrective"]
    assert d1["recall"] < 0.15 < 0.5 < d2["recall"]  # 긴급을 안 쓰는 사이트에서 d1 은 고장을 거의 못 잡는다
    assert all(v["lo"] <= v["score"] <= v["hi"] + 1e-9 for v in res["definitions"].values())
    # 정답과 비교: 이 사이트에서 d1 은 고장을 거의 못 잡는다
    truth = window_labels(world.failures, world.assets, world.cfg.weeks, 4)
    a = world.assets[world.assets["site"] == SITE].reset_index(drop=True)
    pos = {x: i for i, x in enumerate(world.assets["asset"])}
    T = np.array([truth[pos[x], w] == 1 for x in a["asset"] for w in range(logs.n_weeks - 4)])
    true_recall = (L[0] & T).sum() / T.sum()
    assert abs(d1["recall"] - true_recall) < 0.12


def test_estimate_rejects_bad_samples(world, files):
    logs = read_logs(files["wo"], files["assets"], files["cm"], None, weeks=world.cfg.weeks)
    defs = spec.builtin()
    L, index = audit.site_windows(defs, logs.wo_norm, logs.complaints, logs.assets, SITE, logs.n_weeks)
    plan = audit.plan_sample(defs, L, index, SITE, 40, seed=2)
    blank = plan.copy()
    res = audit.estimate_from_sample(
        defs,
        L,
        index,
        pd.concat([blank.iloc[:2], plan.assign(confirmed=truth_for(world, plan)).iloc[2:]]),
        boot=10,
    )
    assert res["n_blank"] == 2
    with pytest.raises(ValueError, match="0 또는 1"):
        audit.estimate_from_sample(defs, L, index, plan.assign(confirmed=2))
    with pytest.raises(ValueError, match="S0"):
        audit.estimate_from_sample(defs, L, index, plan[plan["stratum"] == "S1"].assign(confirmed=1))
    ghost = plan.assign(confirmed=0)
    ghost.loc[0, "asset"] = 99999
    with pytest.raises(ValueError, match="창에 없다"):
        audit.estimate_from_sample(defs, L, index, ghost)


def test_read_logs_validates_inputs(files, tmp_path):
    bad_assets = tmp_path / "bad_assets.csv"
    pd.read_csv(files["assets"]).assign(category="rocket").to_csv(bad_assets, index=False)
    with pytest.raises(ValueError, match="설비 종류"):
        read_logs(files["wo"], bad_assets)
    bad_cm = tmp_path / "bad_cm.csv"
    pd.read_csv(files["cm"]).assign(symptom="아무거나").to_csv(bad_cm, index=False)
    with pytest.raises(ValueError, match="증상"):
        read_logs(files["wo"], files["assets"], bad_cm)
    with pytest.raises(ValueError, match="코드표"):
        book = tmp_path / "book.json"
        book.write_text('{"A1": "urgent"}')
        read_logs(files["wo"], files["assets"], None, book)


def test_dates_are_converted_with_a_shared_origin(tmp_path):
    wo = pd.DataFrame(
        {
            "wo_id": [1, 2],
            "site": [0, 0],
            "asset": [1, 1],
            "created_day": ["2024-03-01", "2024-03-15"],
            "closed_day": ["2024-03-02", "2024-03-16"],
            "type_raw": ["긴급", "긴급"],
        }
    )
    cm = pd.DataFrame({"site": [0], "floor": [3], "day": ["2024-03-08"], "symptom": ["누수"]})
    assets = pd.DataFrame({"asset": [1], "site": [0], "category": ["pump"], "floor": [-1]})
    for name, df in (("wo", wo), ("cm", cm), ("assets", assets)):
        df.to_csv(tmp_path / f"{name}.csv", index=False)
    logs = read_logs(tmp_path / "wo.csv", tmp_path / "assets.csv", tmp_path / "cm.csv")
    assert list(logs.wo_norm["created_day"]) == [0, 14] and list(logs.complaints["day"]) == [7]


def test_cli_end_to_end(world, files, tmp_path):
    out = tmp_path / "sample.csv"
    base = [sys.executable, "-m", "faultline.cli"]
    common = [
        "--work-orders",
        str(files["wo"]),
        "--assets",
        str(files["assets"]),
        "--complaints",
        str(files["cm"]),
        "--weeks",
        str(world.cfg.weeks),
        "--site",
        str(SITE),
    ]
    subprocess.run(
        [*base, "audit-sample", *common, "-n", "120", "-o", str(out)], check=True, capture_output=True
    )
    sample = pd.read_csv(out)
    sample["confirmed"] = truth_for(world, sample)
    sample.to_csv(out, index=False)
    r = subprocess.run(
        [*base, "audit-estimate", *common, "--sample", str(out)], check=True, capture_output=True, text=True
    )
    res = json.loads(r.stdout)
    assert res["pick"] in spec.builtin() and res["n_confirmed"] == len(sample)
    listing = subprocess.run([*base, "definitions"], check=True, capture_output=True, text=True).stdout
    assert "d1_emergency" in listing
