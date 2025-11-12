# NordLayer Telegram Bot - Deployment Guide

## Overview

This guide covers the deployment and configuration of the NordLayer Telegram Bot, which provides an alternative interface for customers to place 3D printing orders through Telegram.

## Architecture

The Telegram Bot is designed as a microservice that integrates with the main NordLayer platform:

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram      │    │  Telegram Bot   │    │   Backend API   │
│   Users         │◄──►│   Service       │◄──►│   (FastAPI)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │  Health Check   │
                       │   Endpoints     │
                       └─────────────────┘
```

## Prerequisites

### System Requirements
- Docker and Docker Compose
- Python 3.11+ (for local development)
- Minimum 512MB RAM
- 1GB disk space for logs and data

### External Dependencies
- Telegram Bot Token (from @BotFather)
- Access to NordLayer Backend API
- Admin Telegram Chat IDs for notifications

## Configuration

### Environment Variables

Create a `.env` file in the telegram-bot directory with the following variables:

```bash
# Required - Telegram Bot Configuration
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Required - API Configuration
API_BASE_URL=http://backend:8000
API_TIMEOUT=30

# Required - Admin Configuration
ADMIN_CHAT_IDS=123456789,987654321

# Optional - Logging Configuration
LOG_LEVEL=INFO
LOG_FILE=logs/bot.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5

# Optional - Production Configuration
ENVIRONMENT=production
DEBUG=false
HEALTH_CHECK_PORT=8080
SHUTDOWN_TIMEOUT=30

# Optional - File Upload Configuration
MAX_FILE_SIZE_MB=50
ALLOWED_FILE_EXTENSIONS=.stl,.obj,.3mf
```

### Getting a Telegram Bot Token

1. Message @BotFather on Telegram
2. Send `/newbot` command
3. Follow the prompts to create your bot
4. Save the token provided by BotFather
5. Configure bot settings:
   ```
   /setname - Set bot name to "NordLayer 3D Printing"
   /setdescription - Set description
   /setabouttext - Set about text
   /setuserpic - Upload bot avatar
   ```

### Finding Admin Chat IDs

1. Add your bot to a group or message it directly
2. Send a message to the bot
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find the `chat.id` in the response
5. Add these IDs to `ADMIN_CHAT_IDS` (comma-separated)

## Deployment Options

### Option 1: Docker Compose (Recommended)

#### Development Deployment
```bash
# Clone the repository
git clone <repository-url>
cd nordlayer-platform

# Create environment file
cp telegram-bot/.env.example telegram-bot/.env
# Edit telegram-bot/.env with your configuration

# Start all services
docker-compose up -d

# Check bot status
curl http://localhost:8080/health
```

#### Production Deployment
```bash
# Use production compose file
docker-compose -f docker-compose.prod.yml up -d

# Check all services
docker-compose -f docker-compose.prod.yml ps

# View bot logs
docker-compose -f docker-compose.prod.yml logs -f telegram-bot
```

### Option 2: Standalone Docker Container

```bash
# Build the image
cd telegram-bot
docker build -t nordlayer-telegram-bot .

# Run the container
docker run -d \
  --name nordlayer-bot \
  --env-file .env \
  -p 8080:8080 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/data:/app/data \
  nordlayer-telegram-bot

# Check health
curl http://localhost:8080/health
```

### Option 3: Local Development

```bash
# Install dependencies
cd telegram-bot
pip install -r requirements.txt

# Create environment file
cp .env.example .env
# Edit .env with your configuration

# Run the bot
python main.py
```

## Health Monitoring

The bot provides several health check endpoints:

### Basic Health Check
```bash
curl http://localhost:8080/health
```
Response:
```json
{
  "status": "healthy",
  "service": "nordlayer-telegram-bot",
  "timestamp": "2024-01-15T10:30:00Z",
  "uptime_seconds": 3600
}
```

### Detailed Status
```bash
curl http://localhost:8080/status
```
Provides comprehensive system information including:
- System metrics (CPU, memory, threads)
- API connectivity status
- Configuration summary
- Service metrics

### Kubernetes Probes
```bash
# Liveness probe
curl http://localhost:8080/live

# Readiness probe
curl http://localhost:8080/ready
```

### Prometheus Metrics
```bash
curl http://localhost:8080/metrics
```

## Logging

### Log Levels
- `DEBUG`: Detailed debugging information
- `INFO`: General operational messages
- `WARNING`: Warning messages
- `ERROR`: Error messages
- `CRITICAL`: Critical errors

### Log Rotation
Logs are automatically rotated when they reach 10MB (configurable):
- Maximum 5 backup files kept
- Compressed backup files
- Automatic cleanup of old logs

### Log Locations
- Container: `/app/logs/bot.log`
- Host (with volume): `./logs/bot.log`

### Viewing Logs
```bash
# Docker Compose
docker-compose logs -f telegram-bot

# Standalone Docker
docker logs -f nordlayer-bot

# Local files
tail -f logs/bot.log
```

## Troubleshooting

### Common Issues

#### Bot Not Responding
1. Check if bot is running: `curl http://localhost:8080/health`
2. Verify Telegram token: Check logs for authentication errors
3. Check API connectivity: `curl http://localhost:8080/status`

#### API Connection Issues
1. Verify `API_BASE_URL` is correct
2. Check if backend service is running
3. Test API directly: `curl http://backend:8000/health`

#### File Upload Failures
1. Check file size limits (`MAX_FILE_SIZE_MB`)
2. Verify allowed extensions (`ALLOWED_FILE_EXTENSIONS`)
3. Check backend API file upload endpoints

#### Memory Issues
1. Monitor memory usage: `curl http://localhost:8080/metrics`
2. Adjust Docker memory limits
3. Check for memory leaks in logs

### Debug Mode

Enable debug mode for detailed logging:
```bash
# Set in .env file
DEBUG=true
LOG_LEVEL=DEBUG

# Restart the bot
docker-compose restart telegram-bot
```

### Log Analysis

Common log patterns to look for:
```bash
# User actions
grep "User action" logs/bot.log

# API calls
grep "API call" logs/bot.log

# Errors
grep "ERROR" logs/bot.log

# System events
grep "bot_started\|bot_shutdown" logs/bot.log
```

## Security Considerations

### Bot Token Security
- Never commit bot tokens to version control
- Use environment variables or secrets management
- Rotate tokens periodically
- Restrict bot permissions in Telegram

### Network Security
- Use HTTPS for webhook mode (if implemented)
- Restrict API access to bot service only
- Use Docker networks for service isolation

### File Upload Security
- Validate file types and sizes
- Scan uploaded files for malware
- Store files in isolated directories
- Implement rate limiting

## Performance Optimization

### Resource Limits
```yaml
# docker-compose.yml
services:
  telegram-bot:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
        reservations:
          memory: 256M
          cpus: '0.25'
```

### Scaling Considerations
- Bot uses polling mode (single instance)
- For high load, consider webhook mode
- Monitor memory and CPU usage
- Implement connection pooling for API calls

## Backup and Recovery

### Data Backup
```bash
# Backup logs
docker cp nordlayer-bot:/app/logs ./backup/logs-$(date +%Y%m%d)

# Backup configuration
cp .env ./backup/env-$(date +%Y%m%d)
```

### Recovery Procedures
1. Stop the bot service
2. Restore configuration files
3. Restore log files (if needed)
4. Restart the bot service
5. Verify health endpoints

## Monitoring and Alerting

### Prometheus Integration
The bot exposes metrics at `/metrics` endpoint:
- `telegram_bot_uptime_seconds`
- `telegram_bot_memory_bytes`
- `telegram_bot_cpu_percent`
- `telegram_bot_api_status`

### Grafana Dashboard
Create dashboards to monitor:
- Bot uptime and availability
- API response times
- Error rates
- Resource usage

### Alerting Rules
Set up alerts for:
- Bot service down
- API connectivity issues
- High error rates
- Resource exhaustion

## Maintenance

### Regular Tasks
- Monitor log file sizes
- Check health endpoints
- Review error logs
- Update dependencies
- Rotate bot tokens

### Updates
```bash
# Pull latest changes
git pull origin main

# Rebuild and restart
docker-compose build telegram-bot
docker-compose up -d telegram-bot

# Verify deployment
curl http://localhost:8080/health
```

### Rollback Procedure
```bash
# Stop current version
docker-compose stop telegram-bot

# Revert to previous image
docker tag nordlayer-telegram-bot:previous nordlayer-telegram-bot:latest

# Start service
docker-compose up -d telegram-bot
```

## Support

### Getting Help
- Check logs first: `docker-compose logs telegram-bot`
- Verify configuration: `curl http://localhost:8080/status`
- Test API connectivity manually
- Review this documentation

### Reporting Issues
When reporting issues, include:
- Bot version and environment
- Relevant log excerpts
- Configuration (without sensitive data)
- Steps to reproduce
- Expected vs actual behavior

### Contact Information
- Technical Support: [support-email]
- Documentation: [docs-url]
- Issue Tracker: [github-issues-url]