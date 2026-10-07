"""README/문서의 숫자를 artifacts 에서 채운다.

문서에 `<!-- num:KEY -->값<!-- /num -->` 마커를 두면 KEY 에 해당하는 실측값으로 바꾼다. `--check` 는 불일치가 있으면 실패한다(CI).
KEY 는 점 경로다: summary.auc.d1 처럼 artifacts/<file>.json 안을 따라간다. 포맷은 `KEY|fmt` (예: |.3f, |.1%, |,d, |pp = 확률×100 소수 1자리).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOCS = [
    "README.md",
    "docs/design.md",
    "docs/definitions.md",
    "docs/evaluation.md",
    "docs/failures.md",
    "docs/simulator.md",
    "docs/real-data.md",
    "docs/research.md",
]
PAT = re.compile(r"<!-- num:([^ ]+?) -->(.*?)<!-- /num -->", re.S)


def resolve(artifacts: Path, key: str):
    """KEY 의 첫 마디가 폴더면 둘째 마디가 파일 이름이다. 아니면 첫 마디가 artifacts/<이름>.json 의 이름이다."""
    parts = key.split(".")
    if (artifacts / parts[0]).is_dir():
        data = json.loads((artifacts / parts[0] / f"{parts[1]}.json").read_text())
        parts = parts[1:]
    else:
        data = json.loads((artifacts / f"{parts[0]}.json").read_text())
    cur = data
    for p in parts[1:]:
        if p == "__len__":
            cur = len(cur)
        elif isinstance(cur, list):
            cur = cur[int(p)]
        else:
            cur = cur[p]
    return cur


def fmt(v, spec: str | None) -> str:
    if spec is None:
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)
    if spec == "s":
        return str(v)
    if spec in ("pp", "pp1", "pp2"):  # 확률 → %p 숫자 (단위 문자는 문서에 직접 쓴다)
        return f"{v * 100:.{2 if spec == 'pp2' else 1}f}"
    if spec.endswith("%"):
        return format(v, spec)
    if spec == ",d":
        return f"{int(round(v)):,}"
    return format(v, spec)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", type=Path, default=Path("artifacts"))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    mismatches, filled = [], 0
    for doc in DOCS:
        p = Path(doc)
        if not p.exists():
            continue
        text = p.read_text()

        def repl(m, doc=doc):
            nonlocal filled
            key, spec = (m.group(1).split("|") + [None])[:2]
            try:
                val = fmt(resolve(a.artifacts, key), spec)
            except Exception as e:  # 산출물 없음 — 그대로 둔다
                if a.check:
                    mismatches.append(f"{doc}: {key} 해석 실패 ({e!r})")
                return m.group(0)
            if val != m.group(2):
                mismatches.append(f"{doc}: {key} 문서={m.group(2)!r} 실측={val!r}")
                filled += 1
            return f"<!-- num:{m.group(1)} -->{val}<!-- /num -->"

        new = PAT.sub(repl, text)
        if not a.check and new != text:
            p.write_text(new)
    if a.check:
        if mismatches:
            print("\n".join(mismatches))
            print(f"{len(mismatches)}개 불일치 — `make numbers` 로 다시 채우세요")
            return 1
        print("docs numbers OK")
        return 0
    print(f"filled {filled} numbers")
    return 0


if __name__ == "__main__":
    sys.exit(main())
