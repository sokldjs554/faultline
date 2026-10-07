PY ?= python
ARTIFACTS ?= artifacts

.PHONY: help install pipeline base quality audit_demo uniform seeds drift robustness summary manifest numbers check-numbers demo demo-gif test lint fmt serve docker clean

help:
	@echo "make install    - 개발용 패키지 설치 (CPU torch 포함)"
	@echo "make pipeline   - 실험 전체를 다시 돌리고 정적 데모와 문서 숫자까지 갱신 (4 vCPU 기준 약 10분)"
	@echo "make test       - 테스트"
	@echo "make serve      - API + 콘솔 (http://localhost:8000/console/)"

install:
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.4"
	$(PY) -m pip install -e ".[dev]"

pipeline: base quality audit_demo uniform seeds drift robustness summary manifest demo numbers

base quality audit_demo uniform seeds drift robustness summary manifest:
	$(PY) scripts/run_all.py --stage $@

numbers:
	$(PY) scripts/fill_numbers.py --artifacts $(ARTIFACTS)
check-numbers:
	$(PY) scripts/fill_numbers.py --artifacts $(ARTIFACTS) --check

demo:
	$(PY) scripts/build_static_demo.py --out docs/demo --artifacts $(ARTIFACTS)

# 정적 데모를 로컬로 띄워 녹화한다 (Playwright + ffmpeg)
demo-gif:
	mkdir -p /tmp/faultline-demo
	cd docs/demo && { $(PY) -m http.server 8020 >/dev/null 2>&1 & echo $$! > /tmp/faultline-demo/server.pid; }
	sleep 2
	node scripts/record_demo.cjs http://localhost:8020 /tmp/faultline-demo / > /tmp/faultline-demo/video.txt 2>&1; \
	kill $$(cat /tmp/faultline-demo/server.pid); \
	ffmpeg -y -loglevel error -ss 0.5 -i "$$(tail -1 /tmp/faultline-demo/video.txt)" -vf "fps=5,scale=860:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=none:diff_mode=rectangle" docs/images/demo.gif; \
	ls -la docs/images/demo.gif

test:
	$(PY) -m pytest -q
lint:
	ruff check src tests scripts && ruff format --check src tests scripts
fmt:
	ruff check --fix src tests scripts && ruff format src tests scripts
serve:
	faultline serve --port 8000
docker:
	docker compose up --build
clean:
	rm -rf $(ARTIFACTS)/*.json docs/demo
