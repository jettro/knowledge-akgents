# Web image: nginx serving the static frontend and proxying /api and /ws to the backend.
#
#   docker build -f knowledge-akgents/docker/web.Dockerfile -t knowledge-akgents-web ..
#
FROM nginx:1.27-alpine

COPY knowledge-akgents/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY knowledge-akgents/frontend/index.html /usr/share/nginx/html/index.html
COPY knowledge-akgents/frontend/app.js /usr/share/nginx/html/app.js
COPY knowledge-akgents/frontend/styles.css /usr/share/nginx/html/styles.css

EXPOSE 80
