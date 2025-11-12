FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    logrotate \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory with proper permissions
RUN mkdir -p /app/logs /app/data

# Create logrotate configuration for bot logs
COPY logrotate.conf /etc/logrotate.d/telegram-bot

# Add health check with improved timeout and retry logic
HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8080/health || exit 1

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash botuser
RUN chown -R botuser:botuser /app
USER botuser

# Expose health check port
EXPOSE 8080

# Use exec form for proper signal handling
CMD ["python", "-u", "main.py"]