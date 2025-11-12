#!/bin/bash

# NordLayer Telegram Bot Startup Script
# This script handles graceful startup with proper signal handling

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    warn "Running as root is not recommended for security reasons"
fi

# Create necessary directories
log "Creating necessary directories..."
mkdir -p /app/logs /app/data

# Set proper permissions
chmod 755 /app/logs /app/data

# Check environment variables
log "Checking environment configuration..."

if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    error "TELEGRAM_BOT_TOKEN environment variable is required"
    exit 1
fi

if [ -z "$API_BASE_URL" ]; then
    warn "API_BASE_URL not set, using default: http://localhost:8000"
    export API_BASE_URL="http://localhost:8000"
fi

if [ -z "$ADMIN_CHAT_IDS" ]; then
    warn "ADMIN_CHAT_IDS not set, admin notifications will be disabled"
fi

# Validate bot token format
if [[ ! "$TELEGRAM_BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]+$ ]]; then
    error "Invalid TELEGRAM_BOT_TOKEN format"
    exit 1
fi

# Test API connectivity (with timeout)
log "Testing API connectivity..."
if command -v curl >/dev/null 2>&1; then
    if ! curl -f -s --max-time 10 "$API_BASE_URL/health" >/dev/null 2>&1; then
        warn "Cannot reach API at $API_BASE_URL - bot will retry automatically"
    else
        log "API connectivity test passed"
    fi
else
    warn "curl not available, skipping API connectivity test"
fi

# Set up signal handlers for graceful shutdown
cleanup() {
    log "Received shutdown signal, stopping bot gracefully..."
    if [ ! -z "$BOT_PID" ]; then
        kill -TERM "$BOT_PID" 2>/dev/null || true
        wait "$BOT_PID" 2>/dev/null || true
    fi
    log "Bot stopped"
    exit 0
}

trap cleanup SIGTERM SIGINT

# Set Python unbuffered output for better logging
export PYTHONUNBUFFERED=1

# Set optimal Python settings for production
export PYTHONHASHSEED=random
export PYTHONDONTWRITEBYTECODE=1

# Log startup information
log "Starting NordLayer Telegram Bot..."
log "Environment: ${ENVIRONMENT:-development}"
log "Log Level: ${LOG_LEVEL:-INFO}"
log "API URL: $API_BASE_URL"
log "Health Check Port: ${HEALTH_CHECK_PORT:-8080}"

# Start the bot
python -u main.py &
BOT_PID=$!

log "Bot started with PID: $BOT_PID"

# Wait for the bot process
wait "$BOT_PID"
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    log "Bot exited normally"
else
    error "Bot exited with code: $EXIT_CODE"
fi

exit $EXIT_CODE