FROM python:3.13-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641
LABEL io.hass.type="addon" io.hass.name="Fast Home Control Dev"
ARG BUILD_VERSION=0.2.0-dev.3
ARG BUILD_ARCH=amd64
LABEL io.hass.version="${BUILD_VERSION}" io.hass.arch="${BUILD_ARCH}"
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
EXPOSE 8099
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/healthz', timeout=2)"]
CMD ["python", "-m", "uvicorn", "fhc.main:app", "--host", "0.0.0.0", "--port", "8099", "--no-proxy-headers", "--no-access-log"]
