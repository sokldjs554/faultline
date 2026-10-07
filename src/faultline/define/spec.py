"""고장 정의 파일(YAML)의 형식과 검증.

정의는 코드가 아니라 파일이다. 고객사 담당자가 읽고 고칠 수 있고, 버전을 붙여 바꾼 이력을 남긴다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path

import yaml

from faultline.quality.contract import KINDS

REQUIRE = ("none", "emergency_or_complaint", "complaint")
EVENT_TIME = ("earliest_evidence", "first_record")


@dataclass(frozen=True)
class Definition:
    name: str
    version: int
    description: str
    wo_kinds: tuple[str, ...]
    wo_require: str
    support_window: tuple[int, int]
    cluster_enabled: bool
    cluster_min_count: int
    cluster_window_days: int
    merge_window_days: int
    event_time: str

    @classmethod
    def from_dict(cls, d: dict) -> Definition:
        try:
            wo = d.get("wo", {})
            cl = (d.get("complaints") or {}).get("cluster") or {}
            sw = (d.get("complaints") or {}).get("support_window_days", [-3, 14])
            if cl.get("require_unique_asset", True) is not True:
                raise ValueError("require_unique_asset 은 true 만 지원한다")
            out = cls(
                name=str(d["name"]),
                version=int(d.get("version", 1)),
                description=str(d.get("description", "")),
                wo_kinds=tuple(wo.get("kinds", [])),
                wo_require=str(wo.get("require", "none")),
                support_window=(int(sw[0]), int(sw[1])),
                cluster_enabled=bool(cl.get("enabled", False)),
                cluster_min_count=int(cl.get("min_count", 3)),
                cluster_window_days=int(cl.get("window_days", 5)),
                merge_window_days=int(d.get("merge_window_days", 7)),
                event_time=str(d.get("event_time", "earliest_evidence")),
            )
        except KeyError as e:
            raise ValueError(f"정의 파일에 필요한 항목이 없다: {e}") from e
        except (TypeError, AttributeError, IndexError) as e:
            raise ValueError(f"정의 파일의 형식이 맞지 않다: {e}") from e
        out.validate()
        return out

    def validate(self) -> None:
        if not self.name:
            raise ValueError("name 이 비어 있다")
        if not self.wo_kinds or any(k not in KINDS or k in ("unknown", "preventive") for k in self.wo_kinds):
            raise ValueError("wo.kinds 는 emergency, corrective 중에서 고른다")
        if self.wo_require not in REQUIRE:
            raise ValueError(f"wo.require 는 {REQUIRE} 중 하나다")
        if self.event_time not in EVENT_TIME:
            raise ValueError(f"event_time 은 {EVENT_TIME} 중 하나다")
        if self.support_window[0] > self.support_window[1]:
            raise ValueError("support_window_days 는 [이전, 이후] 순서로 쓴다")
        if self.merge_window_days < 0 or self.cluster_window_days < 0 or self.cluster_min_count < 1:
            raise ValueError("기간과 개수는 0 이상이어야 한다")

    def to_dict(self) -> dict:
        d = asdict(self)
        return {
            "name": d["name"],
            "version": d["version"],
            "description": d["description"],
            "wo": {"kinds": list(self.wo_kinds), "require": self.wo_require},
            "complaints": {
                "support_window_days": list(self.support_window),
                "cluster": {
                    "enabled": self.cluster_enabled,
                    "min_count": self.cluster_min_count,
                    "window_days": self.cluster_window_days,
                    "require_unique_asset": True,
                },
            },
            "merge_window_days": self.merge_window_days,
            "event_time": self.event_time,
        }


def load_text(text: str) -> Definition:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise ValueError(f"YAML 을 읽을 수 없다: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("정의 파일은 항목과 값이 있는 YAML 이어야 한다")
    return Definition.from_dict(data)


def load_file(path: str | Path) -> Definition:
    return load_text(Path(path).read_text(encoding="utf-8"))


def builtin() -> dict[str, Definition]:
    out: dict[str, Definition] = {}
    root = resources.files("faultline.define").joinpath("builtin")
    for p in sorted(root.iterdir(), key=lambda x: x.name):
        if p.name.endswith(".yaml"):
            d = load_text(p.read_text(encoding="utf-8"))
            out[d.name] = d
    return out


def builtin_text(name: str) -> str:
    root = resources.files("faultline.define").joinpath("builtin")
    for p in root.iterdir():
        if p.name.endswith(".yaml") and load_text(p.read_text(encoding="utf-8")).name == name:
            return p.read_text(encoding="utf-8")
    raise KeyError(name)
