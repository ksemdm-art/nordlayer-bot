"""
Tests for the webhook handler.
"""
import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from webhook_handler import WebhookHandler
from notification_service import NotificationService


class TestWebhookHandler(AioHTTPTestCase):
    """Tests for WebhookHandler"""
    
    async def get_application(self):
        """Create test application"""
        # Mock notification service
        self.mock_notification_service = AsyncMock(spec=NotificationService)
        self.webhook_handler = WebhookHandler(self.mock_notification_service)
        return self.webhook_handler.app
    
    @unittest_run_loop
    async def test_health_check(self):
        """Test health check endpoint"""
        resp = await self.client.request("GET", "/webhook/health")
        
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "telegram_webhook_handler"
        assert "timestamp" in data
    
    @unittest_run_loop
    async def test_handle_new_order_notification(self):
        """Test handling new order notification"""
        payload = {
            "type": "new_order",
            "data": {
                "id": 123,
                "customer_name": "Test Customer",
                "customer_email": "test@example.com",
                "service_name": "FDM Printing",
                "source": "TELEGRAM",
                "specifications": {
                    "telegram_user_id": 456789
                }
            },
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "new_order" in data["message"]
        
        # Verify notification service was called
        self.mock_notification_service.notify_new_order.assert_called_once_with(
            payload["data"], 456789
        )
    
    @unittest_run_loop
    async def test_handle_status_change_notification(self):
        """Test handling status change notification"""
        payload = {
            "type": "status_change",
            "data": {
                "id": 123,
                "customer_name": "Test Customer",
                "customer_email": "test@example.com",
                "service_name": "FDM Printing",
                "status": "ready",
                "source": "TELEGRAM"
            },
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "status_change" in data["message"]
        
        # Verify notification service was called
        self.mock_notification_service.notify_status_change_by_email.assert_called_once_with(
            "test@example.com", payload["data"]
        )
    
    @unittest_run_loop
    async def test_handle_test_notification(self):
        """Test handling test notification"""
        payload = {
            "type": "test",
            "data": {
                "message": "Test notification"
            },
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 200
        data = await resp.json()
        assert data["success"] is True
        assert "test" in data["message"]
        
        # Verify notification service was called
        self.mock_notification_service.send_test_notification.assert_called_once()
    
    @unittest_run_loop
    async def test_handle_unknown_notification_type(self):
        """Test handling unknown notification type"""
        payload = {
            "type": "unknown_type",
            "data": {},
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data
        assert "unknown_type" in data["error"]
    
    @unittest_run_loop
    async def test_handle_invalid_json(self):
        """Test handling invalid JSON payload"""
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 400
        data = await resp.json()
        assert data["error"] == "Invalid JSON"
    
    @unittest_run_loop
    async def test_handle_notification_service_error(self):
        """Test handling notification service errors"""
        # Mock notification service to raise an exception
        self.mock_notification_service.notify_new_order.side_effect = Exception("Service error")
        
        payload = {
            "type": "new_order",
            "data": {
                "id": 123,
                "customer_name": "Test Customer",
                "source": "TELEGRAM"
            },
            "timestamp": "2024-01-01T12:00:00Z"
        }
        
        resp = await self.client.request(
            "POST", 
            "/webhook/notifications",
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"}
        )
        
        assert resp.status == 500
        data = await resp.json()
        assert "error" in data
        assert "Service error" in data["error"]


class TestWebhookHandlerUnit:
    """Unit tests for WebhookHandler methods"""
    
    @pytest.fixture
    def webhook_handler(self):
        """Create webhook handler for testing"""
        mock_notification_service = AsyncMock(spec=NotificationService)
        return WebhookHandler(mock_notification_service)
    
    @pytest.mark.asyncio
    async def test_handle_new_order_web_source(self, webhook_handler):
        """Test handling new order from web source"""
        order_data = {
            "id": 123,
            "customer_name": "Test Customer",
            "source": "WEB"
        }
        
        await webhook_handler._handle_new_order(order_data)
        
        # Should call notify_new_order with user_id=0 for web orders
        webhook_handler.notification_service.notify_new_order.assert_called_once_with(
            order_data, 0
        )
    
    @pytest.mark.asyncio
    async def test_handle_new_order_telegram_source(self, webhook_handler):
        """Test handling new order from Telegram source"""
        order_data = {
            "id": 123,
            "customer_name": "Test Customer",
            "source": "TELEGRAM",
            "specifications": {
                "telegram_user_id": 456789
            }
        }
        
        await webhook_handler._handle_new_order(order_data)
        
        # Should call notify_new_order with extracted user_id
        webhook_handler.notification_service.notify_new_order.assert_called_once_with(
            order_data, 456789
        )
    
    @pytest.mark.asyncio
    async def test_handle_status_change_telegram_order(self, webhook_handler):
        """Test handling status change for Telegram order"""
        order_data = {
            "id": 123,
            "customer_email": "test@example.com",
            "source": "TELEGRAM",
            "status": "ready"
        }
        
        await webhook_handler._handle_status_change(order_data)
        
        # Should call notify_status_change_by_email
        webhook_handler.notification_service.notify_status_change_by_email.assert_called_once_with(
            "test@example.com", order_data
        )
    
    @pytest.mark.asyncio
    async def test_handle_status_change_web_order(self, webhook_handler):
        """Test handling status change for web order"""
        order_data = {
            "id": 123,
            "customer_email": "test@example.com",
            "source": "WEB",
            "status": "ready"
        }
        
        await webhook_handler._handle_status_change(order_data)
        
        # Should not call notification service for web orders
        webhook_handler.notification_service.notify_status_change_by_email.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_test_notification(self, webhook_handler):
        """Test handling test notification"""
        test_data = {"message": "Test"}
        
        await webhook_handler._handle_test_notification(test_data)
        
        # Should call send_test_notification
        webhook_handler.notification_service.send_test_notification.assert_called_once()


# Mock tests for webhook registration
class TestWebhookRegistration:
    """Tests for webhook registration utility"""
    
    @pytest.mark.asyncio
    async def test_register_webhook_url_mock(self):
        """Test webhook URL registration with mocking"""
        from webhook_handler import register_webhook_url
        
        # Test that the function exists and can be called
        # In a real scenario, this would register with the backend
        assert callable(register_webhook_url)


if __name__ == '__main__':
    pytest.main([__file__])