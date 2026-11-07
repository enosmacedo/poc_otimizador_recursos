# Build a partir da raiz do projeto (citele/) para incluir a pasta dados/
FROM node:24-alpine

WORKDIR /app
ENV NODE_ENV=production
COPY citelemap/backend/package.json citelemap/backend/package-lock.json ./
RUN npm ci --omit=dev
COPY citelemap/backend/src ./src
COPY dados ./dados

ENV DADOS_DIR=/app/dados PORTA=3000
EXPOSE 3000
USER node
CMD ["node", "src/server.js"]
