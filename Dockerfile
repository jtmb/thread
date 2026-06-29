# Stage 1: Builder — install Python dependencies into an isolated layer
FROM python:3.12-slim AS builder
WORKDIR /build
COPY thread_server/requirements.txt .
RUN pip install --no-cache-dir --target=/install -r requirements.txt

# Stage 2: Runtime — minimal image, non-root user, production-ready
FROM python:3.12-slim AS runtime

# tini: proper signal forwarding for PID 1 (SIGTERM → graceful Waitress shutdown)
# ca-certificates: TLS validation for any outbound HTTPS calls
RUN apt-get update && \
    apt-get install -y --no-install-recommends tini ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && adduser --system --no-create-home --ingroup appgroup appuser

# Copy installed packages to system path so any user can import them
COPY --from=builder /install /usr/local/lib/python3.12/site-packages/

COPY thread_server/ /app/thread_server/

RUN mkdir -p /app/data && chown -R appuser:appgroup /app

WORKDIR /app
USER appuser

ENV PYTHONPATH="/app"

# Health check uses Python's stdlib urllib — no curl/wget needed in the image
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=10s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health')" || exit 1

EXPOSE 5000

# tini as PID 1 forwards signals to the Python process for graceful shutdown
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "thread_server.server"]
