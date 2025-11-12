"""
Webhook handler for receiving notifications from the backend API.
"""
import logging
import asyncio
from typing import Dict, Any, Optional
from aiohttp import web, ClientSession
from datetime import datetime
import json

from config import settings
from notification_service import NotificationService
from subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)


class WebhookHandler:
    """Handles incoming webhooks from the backend API"""
    
    def __init__(self, notification_service: NotificationService):
        self.notification_service = notification_service
        self.subscription_manager = SubscriptionManager()
        self.app = web.Application()
        self._setup_routes()
        logger.info("Webhook handler initialized")
    
    def _setup_routes(self):
        """Setup webhook routes"""
        self.app.router.add_post('/webhook/notifications', self.handle_notification)
        self.app.router.add_get('/webhook/health', self.health_check)
    
    async def handle_notification(self, request: web.Request) -> web.Response:
        """Handle incoming notification webhook"""
        try:
            # Parse JSON payload
            payload = await request.json()
            notification_type = payload.get('type')
            notification_data = payload.get('data', {})
            timestamp = payload.get('timestamp')
            
            logger.info(f"Received webhook notification: {notification_type}")
            
            if notification_type == "new_order":
                await self._handle_new_order(notification_data)
            elif notification_type == "status_change":
                await self._handle_status_change(notification_data)
            elif notification_type == "test":
                await self._handle_test_notification(notification_data)
            else:
                logger.warning(f"Unknown notification type: {notification_type}")
                return web.json_response(
                    {"error": f"Unknown notification type: {notification_type}"},
                    status=400
                )
            
            return web.json_response({
                "success": True,
                "message": f"Notification {notification_type} processed",
                "processed_at": datetime.now().isoformat()
            })
            
        except json.JSONDecodeError:
            logger.error("Invalid JSON in webhook payload")
            return web.json_response({"error": "Invalid JSON"}, status=400)
        except Exception as e:
            logger.error(f"Error handling webhook notification: {e}")
            return web.json_response(
                {"error": f"Failed to process notification: {str(e)}"},
                status=500
            )
    
    async def _handle_new_order(self, order_data: Dict[str, Any]):
        """Handle new order notification"""
        try:
            # Extract user_id if order came from Telegram
            user_id = None
            source = order_data.get('source')
            
            if source == 'TELEGRAM':
                # Try to find user_id from specifications or other fields
                specs = order_data.get('specifications', {})
                user_id = specs.get('telegram_user_id')
            
            # Send notification to admins
            await self.notification_service.notify_new_order(order_data, user_id or 0)
            
            logger.info(f"New order notification processed for order {order_data.get('id')}")
            
        except Exception as e:
            logger.error(f"Error handling new order notification: {e}")
            raise
    
    async def _handle_status_change(self, order_data: Dict[str, Any]):
        """Handle order status change notification"""
        try:
            customer_email = order_data.get('customer_email')
            order_source = order_data.get('source')
            
            if order_source == 'TELEGRAM' and customer_email:
                # Find all users subscribed to this email and send notifications
                await self.notification_service.notify_status_change_by_email(
                    customer_email, 
                    order_data
                )
            
            logger.info(f"Status change notification processed for order {order_data.get('id')}")
            
        except Exception as e:
            logger.error(f"Error handling status change notification: {e}")
            raise
    
    async def _handle_test_notification(self, data: Dict[str, Any]):
        """Handle test notification"""
        try:
            # Send test notification to admins
            if self.notification_service:
                success = await self.notification_service.send_test_notification()
                logger.info(f"Test notification sent: {success}")
            
        except Exception as e:
            logger.error(f"Error handling test notification: {e}")
            raise
    
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        return web.json_response({
            "status": "healthy",
            "service": "telegram_webhook_handler",
            "timestamp": datetime.now().isoformat()
        })
    
    async def start_server(self, host: str = '0.0.0.0', port: int = 8081):
        """Start the webhook server"""
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, host, port)
            await site.start()
            
            logger.info(f"Webhook server started on {host}:{port}")
            return runner
            
        except Exception as e:
            logger.error(f"Failed to start webhook server: {e}")
            raise
    
    async def stop_server(self, runner: web.AppRunner):
        """Stop the webhook server"""
        try:
            await runner.cleanup()
            logger.info("Webhook server stopped")
        except Exception as e:
            logger.error(f"Error stopping webhook server: {e}")


# Utility function to register webhook URL with backend
async def register_webhook_url(backend_url: str, webhook_url: str) -> bool:
    """Register webhook URL with the backend API"""
    try:
        async with ClientSession() as session:
            payload = {
                "webhook_url": webhook_url,
                "service": "telegram_bot",
                "events": ["new_order", "status_change"]
            }
            
            async with session.post(
                f"{backend_url}/api/v1/webhooks/telegram/notifications",
                json=payload,
                timeout=10
            ) as response:
                if response.status == 200:
                    logger.info(f"Webhook URL registered successfully: {webhook_url}")
                    return True
                else:
                    logger.error(f"Failed to register webhook URL: {response.status}")
                    return False
                    
    except Exception as e:
        logger.error(f"Error registering webhook URL: {e}")
        return False