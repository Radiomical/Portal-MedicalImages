FROM python:3.13.17-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530 AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --require-hashes -r requirements.txt

FROM python:3.13.17-slim-bookworm@sha256:e32be0e55814a08977501ca863271d9bd02443710db8f2afaf8372e2c4508530
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 api api
COPY --chown=10001:10001 blog blog
COPY --chown=10001:10001 users users
COPY --chown=10001:10001 portal portal
COPY --chown=10001:10001 templates templates
COPY --chown=10001:10001 static-src static-src
COPY --chown=10001:10001 manage.py manage.py
RUN mkdir -p /app/.local/static /app/.local/media && chown -R 10001:10001 /app/.local
USER 10001:10001
EXPOSE 8081
# No automatic migrations or production data access at container startup.
CMD ["gunicorn", "portal.wsgi:application", "--bind", "0.0.0.0:8081", "--workers", "2", "--timeout", "90", "--access-logfile", "-", "--error-logfile", "-"]
