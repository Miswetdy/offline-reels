FROM node:24.14.0-alpine3.23 AS dependencies
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.14.0-alpine3.23 AS builder
WORKDIR /app
ARG NEXT_PUBLIC_API_BASE_URL
ARG NEXT_PUBLIC_STAGE7_COLLECTION_TARGET
ARG NEXT_PUBLIC_STAGE8_FIXTURE_MODE
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_STAGE7_COLLECTION_TARGET=$NEXT_PUBLIC_STAGE7_COLLECTION_TARGET
ENV NEXT_PUBLIC_STAGE8_FIXTURE_MODE=$NEXT_PUBLIC_STAGE8_FIXTURE_MODE
COPY --from=dependencies /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:24.14.0-alpine3.23 AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
EXPOSE 3000
CMD ["node", "server.js"]
