FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INTENTFENCE_BACKEND=rules \
    INTENTFENCE_POLICY_PATH=/app/configs/policy.yaml

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
COPY configs ./configs
RUN python -m pip install --no-cache-dir .

USER 65532:65532
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"
CMD ["uvicorn", "intentfence.api:app", "--host", "0.0.0.0", "--port", "8000"]
