# Multi-stage Dockerfile for Vite-based frontend

# Stage 1: Development
FROM node:20-alpine AS development

WORKDIR /app

# Install dependencies
COPY package.json ./

# Use npm install (generates lock file if missing)
RUN npm install

# Copy source code
COPY . .

# Expose Vite dev server port
EXPOSE 8080

# Start Vite dev server with HMR
CMD ["npm", "run", "dev"]

# Stage 2: Build
FROM node:20-alpine AS build

WORKDIR /app

# Install dependencies
COPY package.json ./
RUN npm install

# Copy source code
COPY . .

# Build for production
RUN npm run build

# Stage 3: Production (nginx)
FROM nginx:alpine AS production

# Copy custom nginx config
COPY nginx.conf /etc/nginx/nginx.conf

# Copy built files from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
