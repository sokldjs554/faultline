"""산출물 저장소. artifacts/ 의 JSON 을 읽어 API 가 서빙한다. 실험은 오프라인(scripts/run_all.py)에서 끝난다."""

from __future__ import annotations

import json
import os
from pathlib import Path

NAMES = ("summary", "base", "uniform", "multiseed", "validity", "drift", "quality", "audit_demo", "robustness", "manifest")


def artifact_dir() -> Path:
    return Path(os.environ.get("FAULTLINE_ARTIFACT_DIR", "artifacts"))


class Store:
    def __init__(self, root: Path | None = None):
        self.root = root or artifact_dir()
        self._cache: dict[str, object] = {}

    def artifact(self, name: str):
        if name not in NAMES:
            return None
        if name not in self._cache:
            p = self.root / f"{name}.json"
            if not p.exists():
                return None
            self._cache[name] = json.loads(p.read_text())
        return self._cache[name]

    # 화면 하나가 쓰는 조각만 모아 준다. 정적 데모도 같은 응답을 구워 쓴다.
    def screen(self, name: str):
        base, multi = self.artifact("base"), self.artifact("multiseed")
        if base is None or multi is None:
            return None
        if name == "same-log":
            return {
                "world": {k: v for k, v in base["world"].items() if k != "site_table"},
                "sites": base["world"]["site_table"],
                "timeline": base["timeline"],
                "labels": base["labels"],
                "quality": self.artifact("quality"),
            }
        if name == "ranking":
            uni = self.artifact("uniform")
            return {
                "base": {"models": base["sensitivity"]["models"], "overlap": base["sensitivity"]["overlap"], "topk": base["topk"]},
                "multi": {"base": {k: multi["base"][k] for k in ("seeds", "models", "window", "best_by_own_auc", "best_by_truth_auc", "auc_spread", "d2_beats_d1")}, "uniform": {k: multi["uniform"][k] for k in ("seeds", "models", "auc_spread")}},
                "uniform": None if uni is None else {"models": uni["sensitivity"]["models"], "labels": {n: d["overall"] for n, d in uni["labels"]["definitions"].items()}},
                "validity": self.artifact("validity"),
                "robustness": self.artifact("robustness"),
            }
        if name == "audit":
            return {
                "audit": {k: base["audit"][k] for k in ("n_grid", "p_exact", "p_near", "regret", "n_for_90pct", "names", "beta", "sites")},
                "multi": {"audit": multi["base"].get("audit"), "strategies": multi["base"].get("strategies")},
                "custom": base["custom"],
                "demo": self.artifact("audit_demo"),
                "maturity": base["maturity"],
            }
        if name == "monitor":
            return self.artifact("drift")
        return None
