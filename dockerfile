FROM python:3.11-slim

# --- Ambiente ----------------------------------------------------------------
# TZ=America/Sao_Paulo      as datas gravadas pela aplicação (datetime.now())
#                           passam a ser a hora local, não UTC
# PYTHONUNBUFFERED=1        logs em tempo real no `docker logs`
# PYTHONDONTWRITEBYTECODE=1 não escreve .pyc em execução (funciona com o
#                           sistema de arquivos somente leitura, ver compose)
# O bytecode é compilado no build (mais abaixo), então a inicialização não gasta
# CPU compilando os módulos.
ENV TZ=America/Sao_Paulo \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Somente o necessário para rodar (a imagem deixa de levar docs, testes e
# relatórios para dentro do container)
COPY app.py models.py ./
COPY templates ./templates
COPY static ./static

# Bytecode pré-compilado + pasta de dados (normalmente substituída pelo volume)
RUN python -m compileall -q app.py models.py && mkdir -p dados

EXPOSE 5000

# 1 processo com 4 threads: medido como o melhor equilíbrio memória/CPU para os
# 2 usuários previstos (ver RELATORIO-RECURSOS.md).
#   - 1 worker        -> 1 interpretador Python em memória (2 workers = +40 MB)
#   - gthread 4       -> requisições concorrentes sem bloquear (sync 1 worker
#                        fazia 216 ms de p95 com 2 usuários)
#   - max-requests    -> recicla o worker de vez em quando (limita vazamentos)
# Sem servidor de desenvolvimento: `python app.py` (debug=True) usava 92 MB em
# repouso, o dobro, e expõe o console do Werkzeug.
CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "--threads=4", \
     "--worker-class=gthread", "--timeout=60", "--graceful-timeout=30", \
     "--max-requests=2000", "--max-requests-jitter=200", \
     "--no-control-socket", "app:app"]
