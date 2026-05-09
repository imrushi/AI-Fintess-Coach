# ── Stage 1: build ──────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
# Install adapter-node explicitly (svelte.config.js uses it)
RUN npm install

COPY . .
RUN npm run build

# ── Stage 2: runtime ─────────────────────────────────────────────────────
FROM node:20-alpine AS runner

WORKDIR /app

# Copy only what's needed to run
COPY --from=builder /app/build ./build
COPY --from=builder /app/package.json ./package.json
# adapter-node requires the node_modules at runtime for some deps
COPY --from=builder /app/node_modules ./node_modules

ENV PORT=3000
ENV HOST=0.0.0.0
# Set ORIGIN to the public URL (override via docker-compose env)
ENV ORIGIN=http://localhost

EXPOSE 3000
CMD ["node", "build/index.js"]
