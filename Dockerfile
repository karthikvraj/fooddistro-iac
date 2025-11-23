# Use AWS public ECR mirror for Python to avoid Docker Hub rate limits
FROM public.ecr.aws/docker/library/python:3.11-slim

# Don't write .pyc files and keep stdout/stderr unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Workdir inside the container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Expose port 80 (ECS/ALB will hit this)
EXPOSE 80

# Run the Flask app via gunicorn
CMD ["gunicorn", "-b", "0.0.0.0:80", "app:app"]
