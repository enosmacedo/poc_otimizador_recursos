# ---------- Etapa 1: compila o simulador ARGoS (sem interface grafica) ----------
FROM ubuntu:24.04 AS argos
ARG ARGOS_VERSAO=3.0.0-beta59
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      git ca-certificates cmake make g++ pkg-config \
      liblua5.3-dev libfreeimage-dev libfreeimageplus-dev libgsl-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch ${ARGOS_VERSAO} https://github.com/ilpincy/argos3.git /src/argos3
WORKDIR /src/argos3/build
RUN cmake ../src -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/argos3 \
      -DARGOS_DOCUMENTATION=OFF -DARGOS_BUILD_NATIVE=OFF -DARGOS_INSTALL_LDSOCONF=OFF \
    && make -j"$(nproc)" && make install

# ---------- Etapa 2: citeledrone (Python) + ARGoS ----------
FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      python3 python3-venv liblua5.3-0 libfreeimage3 libfreeimageplus3 libgsl27 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=argos /opt/argos3 /opt/argos3
ENV PATH=/opt/argos3/bin:/opt/venv/bin:$PATH \
    LD_LIBRARY_PATH=/opt/argos3/lib/argos3 \
    ARGOS_PLUGIN_PATH=/opt/argos3/lib/argos3

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /opt/venv && pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY argos ./argos
COPY public ./public

EXPOSE 8090
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8090"]
