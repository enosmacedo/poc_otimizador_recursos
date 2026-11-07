# Build a partir da raiz do projeto (citele/) para incluir dados/rotas/
FROM python:3.14-slim

WORKDIR /app
COPY citeleat/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY citeleat/app ./app
COPY dados/rotas ./dados/rotas

ENV ROTAS_DIR=/app/dados/rotas
EXPOSE 8000
# O GET /calc2dpoligono leva o poligono na URL: aumenta o limite do cabecalho (1 MB)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--http", "h11", "--h11-max-incomplete-event-size", "1048576"]
