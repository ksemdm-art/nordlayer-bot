"""
Enhanced health check server for monitoring bot status and metrics.
"""
import asyncio
import logging
import time
import psutil
import os
from datetime import datetime
from aiohttp import web, ClientSession, ClientTimeout
from config import settings

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """Enhanced HTTP server for health checks and monitoring"""
    
    def __init__(self, port: int = None):
        self.port = port or settings.health_check_port
        self.app = web.Application()
        self.start_time = time.time()
        self.request_count = 0
        self.last_api_check = None
        self.api_status = "unknown"
        
        # Setup routes
        self.app.router.add_get('/health', self.health_check)
        self.app.router.add_get('/status', self.status_check)
        self.app.router.add_get('/metrics', self.metrics_check)
        self.app.router.add_get('/ready', self.readiness_check)
        self.app.router.add_get('/live', self.liveness_check)
    
    async def health_check(self, request):
        """Basic health check endpoint for Docker/K8s"""
        self.request_count += 1
        return web.json_response({
            "status": "healthy",
            "service": "nordlayer-telegram-bot",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(time.time() - self.start_time)
        })
    
    async def liveness_check(self, request):
        """Kubernetes liveness probe - checks if bot is alive"""
        self.request_count += 1
        
        # Check if main process is responsive
        try:
            process = psutil.Process(os.getpid())
            if process.is_running():
                return web.json_response({
                    "status": "alive",
                    "timestamp": datetime.utcnow().isoformat()
                })
            else:
                return web.json_response({
                    "status": "dead",
                    "timestamp": datetime.utcnow().isoformat()
                }, status=503)
        except Exception as e:
            logger.error(f"Liveness check failed: {e}")
            return web.json_response({
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }, status=503)
    
    async def readiness_check(self, request):
        """Kubernetes readiness probe - checks if bot is ready to serve"""
        self.request_count += 1
        
        # Check API connectivity
        api_healthy = await self._check_api_connectivity()
        
        if api_healthy:
            return web.json_response({
                "status": "ready",
                "api_status": "healthy",
                "timestamp": datetime.utcnow().isoformat()
            })
        else:
            return web.json_response({
                "status": "not_ready",
                "api_status": self.api_status,
                "timestamp": datetime.utcnow().isoformat()
            }, status=503)
    
    async def status_check(self, request):
        """Detailed status check with comprehensive information"""
        self.request_count += 1
        
        # Get system metrics
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        # Check API connectivity
        api_healthy = await self._check_api_connectivity()
        
        status = {
            "service": "nordlayer-telegram-bot",
            "version": "1.0.0",
            "environment": settings.environment,
            "status": "healthy" if api_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": int(time.time() - self.start_time),
            "system": {
                "cpu_percent": process.cpu_percent(),
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_percent": process.memory_percent(),
                "threads": process.num_threads(),
                "open_files": len(process.open_files()),
            },
            "api": {
                "url": settings.api_base_url,
                "status": self.api_status,
                "last_check": self.last_api_check.isoformat() if self.last_api_check else None,
                "timeout": settings.api_timeout
            },
            "configuration": {
                "log_level": settings.log_level,
                "admin_count": len(settings.admin_chat_ids_list),
                "max_file_size_mb": settings.max_file_size_mb,
                "allowed_extensions": settings.allowed_extensions_list
            },
            "metrics": {
                "health_requests": self.request_count,
                "start_time": datetime.fromtimestamp(self.start_time).isoformat()
            }
        }
        
        return web.json_response(status)
    
    async def metrics_check(self, request):
        """Prometheus-style metrics endpoint"""
        self.request_count += 1
        
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        
        metrics = [
            f"# HELP telegram_bot_uptime_seconds Bot uptime in seconds",
            f"# TYPE telegram_bot_uptime_seconds counter",
            f"telegram_bot_uptime_seconds {int(time.time() - self.start_time)}",
            "",
            f"# HELP telegram_bot_memory_bytes Memory usage in bytes",
            f"# TYPE telegram_bot_memory_bytes gauge",
            f"telegram_bot_memory_bytes {memory_info.rss}",
            "",
            f"# HELP telegram_bot_cpu_percent CPU usage percentage",
            f"# TYPE telegram_bot_cpu_percent gauge",
            f"telegram_bot_cpu_percent {process.cpu_percent()}",
            "",
            f"# HELP telegram_bot_threads_total Number of threads",
            f"# TYPE telegram_bot_threads_total gauge",
            f"telegram_bot_threads_total {process.num_threads()}",
            "",
            f"# HELP telegram_bot_health_requests_total Health check requests",
            f"# TYPE telegram_bot_health_requests_total counter",
            f"telegram_bot_health_requests_total {self.request_count}",
            "",
            f"# HELP telegram_bot_api_status API connectivity status (1=healthy, 0=unhealthy)",
            f"# TYPE telegram_bot_api_status gauge",
            f"telegram_bot_api_status {1 if self.api_status == 'healthy' else 0}",
        ]
        
        return web.Response(text="\n".join(metrics), content_type="text/plain")
    
    async def _check_api_connectivity(self):
        """Check API connectivity with caching"""
        now = datetime.utcnow()
        
        # Cache API check for 30 seconds
        if (self.last_api_check and 
            (now - self.last_api_check).total_seconds() < 30):
            return self.api_status == "healthy"
        
        try:
            timeout = ClientTimeout(total=5)
            async with ClientSession(timeout=timeout) as session:
                # Try to reach the API health endpoint
                health_url = f"{settings.api_base_url.rstrip('/')}/health"
                async with session.get(health_url) as response:
                    if response.status == 200:
                        self.api_status = "healthy"
                        self.last_api_check = now
                        return True
                    else:
                        self.api_status = f"unhealthy (HTTP {response.status})"
                        self.last_api_check = now
                        return False
        except asyncio.TimeoutError:
            self.api_status = "timeout"
            self.last_api_check = now
            return False
        except Exception as e:
            self.api_status = f"unreachable ({str(e)[:50]})"
            self.last_api_check = now
            return False
    
    async def start(self):
        """Start the health check server"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', self.port)
            await site.start()
            logger.info(f"Health check server started on port {self.port}")
            logger.info(f"Health endpoints available:")
            logger.info(f"  - http://0.0.0.0:{self.port}/health (basic health)")
            logger.info(f"  - http://0.0.0.0:{self.port}/status (detailed status)")
            logger.info(f"  - http://0.0.0.0:{self.port}/metrics (Prometheus metrics)")
            logger.info(f"  - http://0.0.0.0:{self.port}/ready (readiness probe)")
            logger.info(f"  - http://0.0.0.0:{self.port}/live (liveness probe)")
            return runner
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
            raise
    
    async def stop(self, runner):
        """Stop the health check server"""
        try:
            await runner.cleanup()
            logger.info("Health check server stopped")
        except Exception as e:
            logger.error(f"Error stopping health check server: {e}")