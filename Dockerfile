# syntax=docker/dockerfile:1

# --------------------------------------------------------------------------- #
# Builder: create an isolated virtualenv and fetch a pinned, verified helm CLI.
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS builder

ARG HELM_VERSION=v4.2.2
ARG HELM_SHA256=9adafecab4d406853bba163a70e9f104f47dbbf65ce24b7653bae7e36150bcb6

ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies into a self-contained venv.
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install -r requirements.txt gunicorn

# helm CLI — pinned version, checksum-verified (supply-chain integrity).
RUN curl -fsSL -o /tmp/helm.tgz \
        "https://get.helm.sh/helm-${HELM_VERSION}-linux-amd64.tar.gz" \
    && echo "${HELM_SHA256}  /tmp/helm.tgz" | sha256sum -c - \
    && tar -xzf /tmp/helm.tgz -C /tmp \
    && install -m 0755 /tmp/linux-amd64/helm /usr/local/bin/helm \
    && rm -rf /tmp/helm.tgz /tmp/linux-amd64

# --------------------------------------------------------------------------- #
# Runtime: minimal, non-root, no build tools.
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Writable HOME/TMP so the app and gunicorn need no write access to the root
    # filesystem (mount an emptyDir at /tmp when readOnlyRootFilesystem is on).
    HOME=/tmp \
    TMPDIR=/tmp \
    # Secure default: authentication enforced. Override to "disabled" only for
    # local testing (and only on loopback).
    FREELENS_AUTH_MODE=proxy \
    FREELENS_PORT=8050

# Unprivileged user (uid matches deploy/hds securityContext: runAsUser 65532).
RUN groupadd -g 65532 nonroot \
    && useradd -u 65532 -g 65532 -M -s /usr/sbin/nologin nonroot

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /usr/local/bin/helm /usr/local/bin/helm

WORKDIR /app
COPY app.py ./
COPY freelens ./freelens
COPY assets ./assets

USER 65532:65532
EXPOSE 8050

# Liveness via the public, auth-exempt health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('FREELENS_PORT','8050')+'/healthz').read()"]

# gthread workers so the pod-exec WebSocket runs alongside normal requests.
CMD ["gunicorn", "-b", "0.0.0.0:8050", "-k", "gthread", "--threads", "8", \
     "--timeout", "120", "app:server"]
