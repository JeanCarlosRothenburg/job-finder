# Para uso futuro (em outra máquina). No MacBook Air de 8 GB, rode direto com uv: o Docker Desktop
# ocupa 1,5 a 2 GB de RAM e o Ollama no container não usa a GPU do Mac.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    JOBFINDER_DB=/dados/job_finder.db JOBFINDER_PERFIL=/config/perfil.yaml \
    OLLAMA_URL=http://host.docker.internal:11434

WORKDIR /app
COPY pyproject.toml README.md perfil.exemplo.yaml ./
COPY src ./src
RUN pip install --no-cache-dir . && useradd -m app && mkdir -p /dados /config && chown app /dados
USER app

VOLUME ["/dados"]
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/resumo', timeout=5)"
CMD ["job-finder", "serve", "--host", "0.0.0.0", "--port", "8000"]
