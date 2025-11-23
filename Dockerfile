FROM public.ecr.aws/nginx/nginx:stable-alpine

# Remove default NGINX page
RUN rm -rf /usr/share/nginx/html/*

# Copy your custom index page
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80
