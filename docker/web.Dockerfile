# Web image: nginx serving the static frontend and proxying /api and /ws to the backend.
#
#   docker build -f docker/web.Dockerfile -t knowledge-akgents-web .
#
FROM nginx:1.27-alpine

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/*.html /usr/share/nginx/html/
COPY frontend/*.js /usr/share/nginx/html/
COPY frontend/*.css /usr/share/nginx/html/

EXPOSE 80
