# Cached immutable base; upgrade intentionally and rebuild/retest release evidence.
FROM python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/apps/api:/app/bridge HOME=/home/agora
WORKDIR /app
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 agora \
    && useradd --uid 10001 --gid 10001 --create-home agora \
    && mkdir -p /data/artifacts /data/bridge \
    && chown -R 10001:10001 /data
ARG AGORA_SOURCE_SHA256
LABEL org.agora.source-sha256=$AGORA_SOURCE_SHA256
COPY apps/api /app/apps/api
COPY bridge /app/bridge
COPY packages/protocol /app/packages/protocol
COPY infra/pilot /app/infra/pilot
USER 10001:10001

FROM runtime AS api
ENV AGORA_ARTIFACT_STORE_ROOT=/data/artifacts AGORA_API_PORT=8700
EXPOSE 8700
HEALTHCHECK --interval=15s --timeout=8s --start-period=30s --retries=3 \
    CMD ["python", "/app/infra/pilot/readiness.py"]
CMD ["python", "-m", "uvicorn", "agora_api.main:app", "--host", "0.0.0.0", "--port", "8700", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]

FROM runtime AS bridge
ENV AGORA_BRIDGE_HOME=/data/bridge
ENTRYPOINT ["python", "-m", "agora_bridge.cli"]
CMD ["--help"]
