FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY proxy_server.py .

# Create non-root user
RUN useradd -m -u 1001 proxyuser && chown -R proxyuser:proxyuser /app
USER proxyuser

# Expose port
EXPOSE 8080

# Environment defaults
ENV HOST=0.0.0.0
ENV PORT=8080

# Run the application
CMD ["python", "proxy_server.py"]