FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/workspace/backend \
    HOME=/data \
    FLAGS_allocator_strategy=naive_best_fit \
    FLAGS_fraction_of_cpu_memory_to_use=0.05 \
    FLAGS_initial_cpu_memory_in_mb=16 \
    FLAGS_eager_delete_tensor_gb=0.0 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl libgl1 libglib2.0-0 libgomp1 libzbar0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
COPY backend/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY backend /workspace/backend
COPY data /workspace/data

RUN useradd --uid 10001 --create-home --home-dir /home/lmai lmai \
    && mkdir -p /data/uploads /data/generated_reports \
    && chown -R lmai:lmai /data /home/lmai

USER lmai
WORKDIR /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD curl --fail http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]

