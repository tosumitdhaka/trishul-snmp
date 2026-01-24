FROM nginx:alpine

# Copy static assets
COPY src /usr/share/nginx/html

# Copy custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf
