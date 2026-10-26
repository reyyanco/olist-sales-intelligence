# ETL, testler ve dashboard için ortak Python çalışma ortamı.
FROM python:3.11.17-slim-bookworm@sha256:f06d01d4ba3f8ad5af45a3ec87df19c1d317d8e8961edc0fabda61811af6f7cf

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=60 \
    PIP_RETRIES=10

WORKDIR /app

# Kilitli listede tüm bağımlılıklar var; --no-deps ile liste dışı paket gelmez,
# pip check eksik bağımlılık varsa derlemeyi durdurur. pip önbelleği BuildKit
# önbelleğinde tutulur (imaja girmez); yarıda kalan derleme paketleri yeniden indirmez.
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --root-user-action=ignore -r requirements.txt \
    && pip check

RUN useradd --create-home --uid 10001 app

COPY pytest.ini .
COPY etl/ etl/
COPY sql/ sql/
COPY dashboard/ dashboard/
COPY perf/ perf/
COPY tests/ tests/

USER app
