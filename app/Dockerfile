# Non-root, read-only-friendly image for api-llm. Multi-arch (ARM64 on Fargate).
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
COPY app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
# uid 10001 matches the task definition's User. The db file lives in /tmp
# because the root filesystem is read-only in ECS; in AWS DATABASE_URL points
# at RDS anyway.
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin app
USER 10001:10001
ENV DATABASE_URL=sqlite:////tmp/forge.db
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
