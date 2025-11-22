# Very simple NGINX-based container using AWS Public ECR image
FROM public.ecr.aws/nginx/nginx:stable-alpine

# Remove default NGINX page and copy our own
RUN rm -rf /usr/share/nginx/html/*
COPY index.html /usr/share/nginx/html/index.html

# NGINX listens on port 80 by default
EXPOSE 80