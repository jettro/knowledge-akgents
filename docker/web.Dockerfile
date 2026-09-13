# Web image: nginx serving the static frontend and proxying /api and /ws to the backend.
#
#   docker build -f knowledge-akgents/docker/web.Dockerfile -t knowledge-akgents-web ..
#
FROM nginx:1.27-alpine

COPY knowledge-akgents/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY knowledge-akgents/frontend/*.html /usr/share/nginx/html/
COPY knowledge-akgents/frontend/*.js /usr/share/nginx/html/
COPY knowledge-akgents/frontend/*.css /usr/share/nginx/html/

EXPOSE 80
