# faultline — 분석 API + 콘솔 이미지. 산출물(artifacts/)을 이미지에 넣어 두고 서빙한다 (감사 업로드만 즉석 계산).
FROM python:3.12-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --upgrade pip
COPY pyproject.toml README.md ./
COPY src ./src
# 서빙에는 PyTorch 가 필요 없다 (DragonNet 은 오프라인 평가용) — deep 엑스트라를 설치하지 않는다
RUN /opt/venv/bin/pip install .

FROM python:3.12-slim
ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 FAULTLINE_ARTIFACT_DIR=/app/artifacts PORT=8000 OMP_NUM_THREADS=2
RUN useradd -m -u 10001 app && mkdir -p /app/artifacts && chown -R app:app /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app artifacts /app/artifacts
WORKDIR /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health').read()" || exit 1
EXPOSE 8000
CMD ["sh", "-c", "exec uvicorn faultline.api.main:app --host 0.0.0.0 --port ${PORT}"]
