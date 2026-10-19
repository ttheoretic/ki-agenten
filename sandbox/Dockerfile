# Abgeschottete Testumgebung für vom Builder erzeugten Code (ohne Netzwerk ausgeführt).
#   docker build -t aicompany-sandbox sandbox/
# Danach nutzt der Builder automatisch Docker (builder.execution = "auto").
FROM python:3.12-slim
RUN pip install --no-cache-dir fastapi==0.146.0 uvicorn==0.54.0 pydantic==2.14.1 pytest==9.1.1 httpx==0.28.1
USER 65534:65534
WORKDIR /app
