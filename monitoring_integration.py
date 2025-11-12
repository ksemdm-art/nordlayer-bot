"""
Monitoring integration for Telegram bot.
"""
import logging
import json
import time
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
import asyncio
import aiohttp

from logging_config import setup_structured_logging

# Setup structured logging for the bot
logger = setup_structured_logging("telegram_bot")

@dataclass
class BotMetrics:
    """Bot performance metrics."""
    messages_processed: int = 0
    orders_created: int = 0
    errors_count: int = 0
    api_calls_count: int = 0
    api_errors_count: int = 0
    average_response_time: float = 0.0
    active_sessions: int = 0
    uptime_seconds: int = 0

class BotMonitoring:
    """Monitoring system for Telegram bot."""
    
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url
        self.metrics = BotMetrics()
        self.start_time = time.time()
        self.response_times = []
        self.session = None
        
    async def initialize(self):
        """Initialize monitoring session."""
        self.session = aiohttp.ClientSession()
        logger.info("Bot monitoring initialized")
    
    async def cleanup(self):
        """Cleanup monitoring resources."""
        if self.session:
            await self.session.close()
        logger.info("Bot monitoring cleaned up")
    
    def record_message_processed(self, user_id: int, message_type: str, 
                                processing_time: float):
        """Record a processed message."""
        self.metrics.messages_processed += 1
        self.response_times.append(processing_time)
        
        # Keep only last 100 response times for average calculation
        if len(self.response_times) > 100:
            self.response_times.pop(0)
        
        self.metrics.average_response_time = sum(self.response_times) / len(self.response_times)
        
        logger.info(
            "Message processed",
            extra={
                'user_id': user_id,
                'message_type': message_type,
                'processing_time_ms': processing_time * 1000,
                'total_messages': self.metrics.messages_processed
            }
        )
    
    def record_order_created(self, user_id: int, order_id: str, service_id: int):
        """Record a successful order creation."""
        self.metrics.orders_created += 1
        
        logger.info(
            "Order created via bot",
            extra={
                'user_id': user_id,
                'order_id': order_id,
                'service_id': service_id,
                'total_orders': self.metrics.orders_created
            }
        )
    
    def record_error(self, error: Exception, context: Dict[str, Any] = None):
        """Record an error occurrence."""
        self.metrics.errors_count += 1
        
        error_context = {
            'error_type': type(error).__name__,
            'error_message': str(error),
            'total_errors': self.metrics.errors_count
        }
        
        if context:
            error_context.update(context)
        
        logger.error(
            "Bot error occurred",
            extra=error_context,
            exc_info=True
        )
    
    def record_api_call(self, endpoint: str, method: str, status_code: int, 
                       duration: float, success: bool = True):
        """Record an API call."""
        self.metrics.api_calls_count += 1
        
        if not success or status_code >= 400:
            self.metrics.api_errors_count += 1
        
        logger.info(
            "API call made",
            extra={
                'endpoint': endpoint,
                'method': method,
                'status_code': status_code,
                'duration_ms': duration * 1000,
                'success': success,
                'total_api_calls': self.metrics.api_calls_count,
                'api_error_rate': self.metrics.api_errors_count / self.metrics.api_calls_count
            }
        )
    
    def update_active_sessions(self, count: int):
        """Update active sessions count."""
        self.metrics.active_sessions = count
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics."""
        current_time = time.time()
        self.metrics.uptime_seconds = int(current_time - self.start_time)
        
        return {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'metrics': asdict(self.metrics),
            'health': {
                'status': 'healthy' if self.metrics.errors_count < 10 else 'degraded',
                'error_rate': (
                    self.metrics.errors_count / max(self.metrics.messages_processed, 1)
                ),
                'api_error_rate': (
                    self.metrics.api_errors_count / max(self.metrics.api_calls_count, 1)
                )
            }
        }
    
    async def send_metrics_to_backend(self):
        """Send metrics to backend monitoring system."""
        if not self.session:
            return
        
        try:
            metrics_data = self.get_metrics()
            
            async with self.session.post(
                f"{self.api_base_url}/api/v1/monitoring/bot-metrics",
                json=metrics_data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    logger.debug("Metrics sent to backend successfully")
                else:
                    logger.warning(f"Failed to send metrics: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Error sending metrics to backend: {e}")
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check."""
        try:
            # Test API connectivity
            async with self.session.get(
                f"{self.api_base_url}/api/v1/health",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as response:
                api_healthy = response.status == 200
        except Exception:
            api_healthy = False
        
        metrics = self.get_metrics()
        health_status = metrics['health']
        
        overall_status = 'healthy'
        if not api_healthy:
            overall_status = 'degraded'
        elif health_status['error_rate'] > 0.1:  # 10% error rate
            overall_status = 'degraded'
        elif self.metrics.errors_count > 50:
            overall_status = 'unhealthy'
        
        return {
            'status': overall_status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'components': {
                'bot': {
                    'status': 'healthy' if self.metrics.errors_count < 10 else 'degraded',
                    'uptime_seconds': self.metrics.uptime_seconds,
                    'messages_processed': self.metrics.messages_processed,
                    'error_rate': health_status['error_rate']
                },
                'api_connectivity': {
                    'status': 'healthy' if api_healthy else 'unhealthy',
                    'api_calls': self.metrics.api_calls_count,
                    'api_error_rate': health_status['api_error_rate']
                }
            }
        }

class MonitoringMiddleware:
    """Middleware for monitoring bot handlers."""
    
    def __init__(self, monitoring: BotMonitoring):
        self.monitoring = monitoring
    
    def __call__(self, handler):
        """Decorator for monitoring handler execution."""
        async def wrapper(update, context):
            start_time = time.time()
            user_id = update.effective_user.id if update.effective_user else None
            handler_name = handler.__name__
            
            try:
                result = await handler(update, context)
                
                # Record successful processing
                processing_time = time.time() - start_time
                self.monitoring.record_message_processed(
                    user_id, handler_name, processing_time
                )
                
                return result
                
            except Exception as e:
                # Record error
                self.monitoring.record_error(e, {
                    'handler': handler_name,
                    'user_id': user_id,
                    'update_type': type(update).__name__
                })
                raise
        
        return wrapper

# Global monitoring instance
bot_monitoring = None

def get_bot_monitoring() -> Optional[BotMonitoring]:
    """Get the global bot monitoring instance."""
    return bot_monitoring

def setup_bot_monitoring(api_base_url: str) -> BotMonitoring:
    """Setup bot monitoring."""
    global bot_monitoring
    bot_monitoring = BotMonitoring(api_base_url)
    return bot_monitoring

async def start_metrics_reporting_loop(monitoring: BotMonitoring, interval: int = 60):
    """Start periodic metrics reporting to backend."""
    while True:
        try:
            await monitoring.send_metrics_to_backend()
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in metrics reporting loop: {e}")
            await asyncio.sleep(interval)

# Health check endpoint for the bot (if running as web service)
async def bot_health_endpoint():
    """Health check endpoint for the bot."""
    if bot_monitoring:
        return await bot_monitoring.health_check()
    else:
        return {
            'status': 'unhealthy',
            'error': 'Monitoring not initialized'
        }