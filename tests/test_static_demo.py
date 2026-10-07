import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_static_demo_builds_and_covers_every_get_the_console_makes(tmp_path):
    out = tmp_path / "demo"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_static_demo.py"),
            "--out",
            str(out),
            "--artifacts",
            str(ROOT / "artifacts"),
        ],
        check=True,
        cwd=ROOT,
    )
    html = (out / "index.html").read_text()
    assert "FAULTLINE_STATIC = true" in html
    for f in ("app.js", "charts.js", "style.css", ".nojekyll"):
        assert (out / f).exists()
    baked = {p.stem for p in (out / "api").glob("*.json")}
    for p in (out / "api").glob("*.json"):
        json.loads(p.read_text())
    app = (ROOT / "src/faultline/console/app.js").read_text()
    # POST 와 업로드는 정적 데모에서 막혀 있으므로, 인자 없이 부르는 GET 경로만 확인한다
    wanted = set(re.findall(r'api\("(/[^"]+)"\)', app))
    assert wanted, "app.js 에서 api() 호출을 찾지 못했다"
    missing = [w for w in wanted if w.lstrip("/").replace("/", "_") not in baked]
    assert not missing, missing
