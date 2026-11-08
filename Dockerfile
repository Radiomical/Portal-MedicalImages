# Match the runtime's Debian/Python ABI. All base images are immutable.
FROM python:3.13.17-slim-trixie@sha256:d98cc29d3266e535dd9da1099688d9cb3ca4753813571e071763d17725460962 AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --require-hashes -r requirements.txt
# Distroless Python lives in /usr/bin, not the builder's /usr/local/bin.
RUN rm /opt/venv/bin/python /opt/venv/bin/python3 /opt/venv/bin/python3.13 \
    && ln -s /usr/bin/python3 /opt/venv/bin/python \
    && ln -s /usr/bin/python3 /opt/venv/bin/python3 \
    && ln -s /usr/bin/python3 /opt/venv/bin/python3.13 \
    && sed -i 's|home = /usr/local/bin|home = /usr/bin|' /opt/venv/pyvenv.cfg \
    && mkdir -p /runtime/static /runtime/media /runtime/private-dicom

FROM gcr.io/distroless/python3-debian13:nonroot@sha256:c3ed2b61f3c4e410685565ceb3c818197b552832521b39d53eca5d2d9d0dc1e1
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --from=builder --chown=65532:65532 /runtime /app/.local
COPY api api
COPY blog blog
COPY users users
COPY portal portal
COPY templates templates
COPY static-src static-src
COPY manage.py manage.py
USER 65532:65532
EXPOSE 8081
# No shell, pip, automatic migrations or production data access at startup.
ENTRYPOINT ["/opt/venv/bin/python"]
CMD ["-m", "gunicorn", "portal.wsgi:application", "--bind", "0.0.0.0:8081", "--workers", "2", "--timeout", "90", "--access-logfile", "-", "--error-logfile", "-"]
