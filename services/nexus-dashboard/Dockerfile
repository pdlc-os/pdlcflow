# Nexus Dashboard — Streamlit ops console over pdlcflow OTel signals.
FROM python:3.12-slim

WORKDIR /app

# Streamlit + data deps only; this service talks HTTP to Prometheus/Tempo, so it
# needs no pdlcflow packages.
COPY services/nexus-dashboard/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY services/nexus-dashboard/app.py ./app.py

EXPOSE 8501
HEALTHCHECK --interval=15s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')" || exit 1

ENTRYPOINT ["streamlit", "run", "app.py", \
  "--server.port=8501", "--server.address=0.0.0.0", \
  "--server.headless=true", "--browser.gatherUsageStats=false"]
