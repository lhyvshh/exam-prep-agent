FROM node:22-slim

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    EXAM_PREP_BACKEND_URL=http://backend:8000

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
