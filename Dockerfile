FROM python:3.13.9-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

COPY pyproject.toml README.md requirements-executed.txt ./
COPY src ./src
COPY data/README.md ./data/README.md

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --timeout 120 --retries 10 -c requirements-executed.txt -e '.[app,model]'
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY data/snapshots/afijio_public_primary_arcgis.json ./data/raw/afijio_public_primary_arcgis.json
RUN python -m supplysignal.pipeline \
    && python -m supplysignal.baseline \
    && python -m supplysignal.train \
    && python -m supplysignal.inference \
    && python -m supplysignal.ranking_eval \
    && python -m supplysignal.workload_eval \
    && python -m supplysignal.decisions
COPY data/example_lmis_input.csv data/example_roster.csv data/example_mapping.json ./data/
COPY data/snapshots/afijio_basemap.jpg data/snapshots/afijio_basemap.json ./data/snapshots/
COPY .streamlit ./.streamlit
COPY app ./app

EXPOSE 8501
CMD ["streamlit", "run", "app/main.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
