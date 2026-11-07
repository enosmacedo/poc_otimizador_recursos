FROM python:3.14-slim

WORKDIR /app
RUN pip install --no-cache-dir geopandas==1.2.0 pyogrio==0.13.0 osmnx==2.1.1
COPY preparar_dados.py preparar_areas.py preparar_rotas.py ./
