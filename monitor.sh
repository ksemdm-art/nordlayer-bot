#!/bin/bash

# NordLayer Telegram Bot Monitoring Script
# This script provides monitoring and health check capabilities

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
HEALTH_URL="http://localhost:8080"
LOG_FILE="logs/bot.log"
ALERT_EMAIL=""  # Set this for email alerts

# Functions
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

error() {
    echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

info() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $1${NC}"
}

# Check if curl is available
check_curl() {
    if ! command -v curl >/dev/null 2>&1; then
        error "curl is required but not installed"
        exit 1
    fi
}

# Check bot health
check_health() {
    local response
    local status_code
    
    response=$(curl -s -w "%{http_code}" "$HEALTH_URL/health" 2>/dev/null || echo "000")
    status_code="${response: -3}"
    
    if [ "$status_code" = "200" ]; then
        log "Health check: HEALTHY"
        return 0
    else
        error "Health check: UNHEALTHY (HTTP $status_code)"
        return 1
    fi
}

# Get detailed status
get_status() {
    local response
    
    response=$(curl -s "$HEALTH_URL/status" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "$response" | python3 -m json.tool 2>/dev/null || echo "$response"
    else
        error "Failed to get status information"
        return 1
    fi
}

# Get metrics
get_metrics() {
    local response
    
    response=$(curl -s "$HEALTH_URL/metrics" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        echo "$response"
    else
        error "Failed to get metrics"
        return 1
    fi
}

# Check log file
check_logs() {
    if [ ! -f "$LOG_FILE" ]; then
        warn "Log file not found: $LOG_FILE"
        return 1
    fi
    
    local log_size=$(du -h "$LOG_FILE" | cut -f1)
    local error_count=$(grep -c "ERROR" "$LOG_FILE" 2>/dev/null || echo "0")
    local warning_count=$(grep -c "WARNING" "$LOG_FILE" 2>/dev/null || echo "0")
    
    info "Log file size: $log_size"
    info "Recent errors: $error_count"
    info "Recent warnings: $warning_count"
    
    # Show recent errors
    if [ "$error_count" -gt 0 ]; then
        warn "Recent errors:"
        tail -n 100 "$LOG_FILE" | grep "ERROR" | tail -n 5
    fi
}

# Check system resources
check_resources() {
    if command -v docker >/dev/null 2>&1; then
        local container_id=$(docker ps -q -f name=telegram-bot)
        
        if [ ! -z "$container_id" ]; then
            info "Docker container stats:"
            docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" "$container_id"
        else
            warn "Telegram bot container not found"
        fi
    fi
    
    # System resources
    if command -v free >/dev/null 2>&1; then
        info "System memory:"
        free -h
    fi
    
    if command -v df >/dev/null 2>&1; then
        info "Disk usage:"
        df -h | grep -E "(Filesystem|/dev/)"
    fi
}

# Send alert (placeholder for email/webhook integration)
send_alert() {
    local message="$1"
    local severity="${2:-WARNING}"
    
    warn "ALERT [$severity]: $message"
    
    # Add email/webhook/Slack notification here
    if [ ! -z "$ALERT_EMAIL" ]; then
        echo "$message" | mail -s "NordLayer Bot Alert [$severity]" "$ALERT_EMAIL" 2>/dev/null || true
    fi
}

# Continuous monitoring
monitor_continuous() {
    local interval="${1:-60}"  # Default 60 seconds
    local failure_count=0
    local max_failures=3
    
    log "Starting continuous monitoring (interval: ${interval}s)"
    
    while true; do
        if check_health; then
            failure_count=0
        else
            failure_count=$((failure_count + 1))
            
            if [ $failure_count -ge $max_failures ]; then
                send_alert "Bot health check failed $failure_count times" "CRITICAL"
                failure_count=0  # Reset to avoid spam
            fi
        fi
        
        sleep "$interval"
    done
}

# Show usage
usage() {
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  health      - Check bot health"
    echo "  status      - Get detailed status"
    echo "  metrics     - Get Prometheus metrics"
    echo "  logs        - Check log file status"
    echo "  resources   - Check system resources"
    echo "  monitor     - Start continuous monitoring"
    echo "  all         - Run all checks"
    echo ""
    echo "Options:"
    echo "  --interval N  - Set monitoring interval in seconds (default: 60)"
    echo "  --help        - Show this help"
}

# Main script
main() {
    check_curl
    
    case "${1:-all}" in
        "health")
            check_health
            ;;
        "status")
            get_status
            ;;
        "metrics")
            get_metrics
            ;;
        "logs")
            check_logs
            ;;
        "resources")
            check_resources
            ;;
        "monitor")
            monitor_continuous "${2:-60}"
            ;;
        "all")
            log "Running comprehensive health check..."
            echo ""
            
            info "=== Health Check ==="
            check_health
            echo ""
            
            info "=== Log Analysis ==="
            check_logs
            echo ""
            
            info "=== System Resources ==="
            check_resources
            echo ""
            
            info "=== Detailed Status ==="
            get_status
            ;;
        "--help"|"help")
            usage
            ;;
        *)
            error "Unknown command: $1"
            usage
            exit 1
            ;;
    esac
}

# Handle script arguments
if [ "$1" = "--interval" ]; then
    shift
    INTERVAL="$1"
    shift
    main "$@" "$INTERVAL"
else
    main "$@"
fi