"""
Tests for order tracking functionality in the Telegram bot.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, CallbackQuery, Chat
from telegram.ext import ContextTypes

from api_client import APIClient, APIClientError
from main import TelegramBot
from session_manager import SessionManager
from notification_service import NotificationService


class TestOrderTracking:
    """Test cases for order tracking functionality"""
    
    @pytest.fixture
    def mock_api_client(self):
        """Mock API client for testing"""
        client = AsyncMock(spec=APIClient)
        return client
    
    @pytest.fixture
    def mock_notification_service(self):
        """Mock notification service for testing"""
        service = AsyncMock(spec=NotificationService)
        return service
    
    @pytest.fixture
    def telegram_bot(self, mock_api_client, mock_notification_service):
        """Create telegram bot instance for testing"""
        bot = TelegramBot()
        bot.api_client = mock_api_client
        bot.notification_service = mock_notification_service
        bot.session_manager = SessionManager()
        return bot
    
    @pytest.fixture
    def mock_update(self):
        """Create mock telegram update"""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.first_name = "Test User"
        update.message = MagicMock(spec=Message)
        update.message.reply_text = AsyncMock()
        update.callback_query = None
        return update
    
    @pytest.fixture
    def mock_callback_update(self):
        """Create mock telegram callback update"""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.first_name = "Test User"
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.answer = AsyncMock()
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message = MagicMock(spec=Message)
        update.callback_query.message.reply_text = AsyncMock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create mock context"""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.user_data = {}
        return context
    
    @pytest.mark.asyncio
    async def test_start_order_tracking(self, telegram_bot, mock_update, mock_context):
        """Test starting order tracking process"""
        await telegram_bot.start_order_tracking(mock_update, mock_context)
        
        # Check that tracking state is set
        assert mock_context.user_data['tracking_state'] == 'waiting_for_email'
        
        # Check that message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Отслеживание заказов" in call_args[0][0]
    
    @pytest.mark.asyncio
    async def test_handle_tracking_email_valid(self, telegram_bot, mock_update, mock_context):
        """Test handling valid email for tracking"""
        # Setup
        mock_context.user_data['tracking_state'] = 'waiting_for_email'
        test_email = "test@example.com"
        
        # Mock API response with orders
        mock_orders = [
            {
                'id': 1,
                'status': 'new',
                'service_name': 'FDM Printing',
                'created_at': '2024-01-15T10:00:00Z',
                'customer_name': 'Test User'
            },
            {
                'id': 2,
                'status': 'in_progress',
                'service_name': 'SLA Printing',
                'created_at': '2024-01-10T15:30:00Z',
                'customer_name': 'Test User'
            }
        ]
        telegram_bot.api_client.get_orders_by_email.return_value = mock_orders
        
        # Mock loading message
        loading_message = AsyncMock()
        loading_message.delete = AsyncMock()
        mock_update.message.reply_text.return_value = loading_message
        
        await telegram_bot.handle_tracking_email(mock_update, mock_context, test_email)
        
        # Verify API was called with correct email
        telegram_bot.api_client.get_orders_by_email.assert_called_once_with(test_email)
        
        # Verify tracking state was cleared
        assert 'tracking_state' not in mock_context.user_data
        
        # Verify loading message was deleted
        loading_message.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_handle_tracking_email_invalid(self, telegram_bot, mock_update, mock_context):
        """Test handling invalid email for tracking"""
        mock_context.user_data['tracking_state'] = 'waiting_for_email'
        invalid_email = "invalid-email"
        
        await telegram_bot.handle_tracking_email(mock_update, mock_context, invalid_email)
        
        # Verify error message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        assert "Некорректный email" in call_args[0][0]
        
        # Verify API was not called
        telegram_bot.api_client.get_orders_by_email.assert_not_called()
        
        # Verify tracking state was not cleared (user can try again)
        assert mock_context.user_data['tracking_state'] == 'waiting_for_email'
    
    @pytest.mark.asyncio
    async def test_handle_tracking_email_no_orders(self, telegram_bot, mock_update, mock_context):
        """Test handling email with no orders found"""
        mock_context.user_data['tracking_state'] = 'waiting_for_email'
        test_email = "noorders@example.com"
        
        # Mock API response with empty list
        telegram_bot.api_client.get_orders_by_email.return_value = []
        
        # Mock loading message
        loading_message = AsyncMock()
        loading_message.delete = AsyncMock()
        mock_update.message.reply_text.return_value = loading_message
        
        await telegram_bot.handle_tracking_email(mock_update, mock_context, test_email)
        
        # Verify API was called
        telegram_bot.api_client.get_orders_by_email.assert_called_once_with(test_email)
        
        # Verify "no orders found" message was sent
        assert mock_update.message.reply_text.call_count == 2  # Loading + no orders message
        call_args = mock_update.message.reply_text.call_args_list[1]
        assert "Заказы не найдены" in call_args[0][0]
        
        # Verify tracking state was cleared
        assert 'tracking_state' not in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_handle_tracking_email_api_error(self, telegram_bot, mock_update, mock_context):
        """Test handling API error during email tracking"""
        mock_context.user_data['tracking_state'] = 'waiting_for_email'
        test_email = "test@example.com"
        
        # Mock API error
        telegram_bot.api_client.get_orders_by_email.side_effect = APIClientError("API Error", 500)
        
        # Mock loading message
        loading_message = AsyncMock()
        loading_message.delete = AsyncMock()
        mock_update.message.reply_text.return_value = loading_message
        
        with patch('telegram_bot.main.BotErrorHandler.handle_api_error') as mock_error_handler:
            mock_error_handler.return_value = AsyncMock()
            
            await telegram_bot.handle_tracking_email(mock_update, mock_context, test_email)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
        
        # Verify tracking state was cleared
        assert 'tracking_state' not in mock_context.user_data
    
    @pytest.mark.asyncio
    async def test_show_orders_list(self, telegram_bot, mock_update, mock_context):
        """Test showing orders list"""
        test_email = "test@example.com"
        mock_orders = [
            {
                'id': 1,
                'status': 'new',
                'service_name': 'FDM Printing',
                'created_at': '2024-01-15T10:00:00Z',
                'customer_name': 'Test User'
            },
            {
                'id': 2,
                'status': 'completed',
                'service_name': 'SLA Printing',
                'created_at': '2024-01-10T15:30:00Z',
                'customer_name': 'Test User'
            }
        ]
        
        await telegram_bot.show_orders_list(mock_update, mock_context, mock_orders, test_email)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        
        # Check message content
        message_text = call_args[0][0]
        assert "Ваши заказы (2)" in message_text
        assert test_email in message_text
        assert "Заказ #1" in message_text
        assert "Заказ #2" in message_text
        
        # Check reply markup (keyboard)
        reply_markup = call_args[1]['reply_markup']
        assert reply_markup is not None
        
        # Verify keyboard has order detail buttons
        keyboard = reply_markup.inline_keyboard
        order_buttons = [btn for row in keyboard for btn in row if btn.callback_data.startswith('order_details_')]
        assert len(order_buttons) == 2
    
    @pytest.mark.asyncio
    async def test_show_order_details(self, telegram_bot, mock_callback_update, mock_context):
        """Test showing order details"""
        order_id = 123
        
        await telegram_bot.show_order_details(mock_callback_update, mock_context, order_id)
        
        # Verify message was sent/edited
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_update.callback_query.edit_message_text.call_args
        
        # Check message content
        message_text = call_args[1]['text']
        assert f"Заказ #{order_id}" in message_text
    
    @pytest.mark.asyncio
    async def test_track_command(self, telegram_bot, mock_update, mock_context):
        """Test /track command"""
        with patch.object(telegram_bot, 'start_order_tracking') as mock_start_tracking:
            mock_start_tracking.return_value = AsyncMock()
            
            await telegram_bot.track_command(mock_update, mock_context)
            
            # Verify start_order_tracking was called
            mock_start_tracking.assert_called_once_with(mock_update, mock_context)
    
    def test_validate_email(self, telegram_bot):
        """Test email validation"""
        # Valid emails
        assert telegram_bot._validate_email("test@example.com") == True
        assert telegram_bot._validate_email("user.name@domain.co.uk") == True
        assert telegram_bot._validate_email("test+tag@example.org") == True
        
        # Invalid emails
        assert telegram_bot._validate_email("") == False
        assert telegram_bot._validate_email("invalid-email") == False
        assert telegram_bot._validate_email("@example.com") == False
        assert telegram_bot._validate_email("test@") == False
        assert telegram_bot._validate_email("test.example.com") == False
    
    @pytest.mark.asyncio
    async def test_callback_query_tracking_handlers(self, telegram_bot, mock_callback_update, mock_context):
        """Test callback query handlers for tracking"""
        # Test track_order callback
        mock_callback_update.callback_query.data = "track_order"
        
        with patch.object(telegram_bot, 'start_order_tracking') as mock_start_tracking:
            mock_start_tracking.return_value = AsyncMock()
            
            await telegram_bot.handle_callback_query(mock_callback_update, mock_context)
            
            mock_start_tracking.assert_called_once()
        
        # Test cancel_tracking callback
        mock_callback_update.callback_query.data = "cancel_tracking"
        mock_context.user_data['tracking_state'] = 'waiting_for_email'
        
        with patch.object(telegram_bot, 'show_main_menu') as mock_main_menu:
            mock_main_menu.return_value = AsyncMock()
            
            await telegram_bot.handle_callback_query(mock_callback_update, mock_context)
            
            # Verify tracking state was cleared
            assert 'tracking_state' not in mock_context.user_data
            mock_main_menu.assert_called_once()
        
        # Test order_details callback
        mock_callback_update.callback_query.data = "order_details_123"
        
        with patch.object(telegram_bot, 'show_order_details') as mock_order_details:
            mock_order_details.return_value = AsyncMock()
            
            await telegram_bot.handle_callback_query(mock_callback_update, mock_context)
            
            mock_order_details.assert_called_once_with(mock_callback_update, mock_context, 123)


class TestAPIClientOrderSearch:
    """Test cases for API client order search functionality"""
    
    @pytest.fixture
    def api_client(self):
        """Create API client for testing"""
        return APIClient("http://test-api.com")
    
    @pytest.mark.asyncio
    async def test_get_orders_by_email_success(self, api_client):
        """Test successful order search by email"""
        test_email = "test@example.com"
        mock_response = {
            "success": True,
            "data": [
                {"id": 1, "status": "new", "customer_email": test_email},
                {"id": 2, "status": "completed", "customer_email": test_email}
            ]
        }
        
        with patch.object(api_client, '_make_request') as mock_request:
            mock_request.return_value = mock_response
            
            result = await api_client.get_orders_by_email(test_email)
            
            # Verify request was made correctly
            mock_request.assert_called_once_with(
                "GET", 
                "/api/v1/orders/search", 
                params={"email": test_email}
            )
            
            # Verify result
            assert len(result) == 2
            assert result[0]["id"] == 1
            assert result[1]["id"] == 2
    
    @pytest.mark.asyncio
    async def test_get_orders_by_email_empty_result(self, api_client):
        """Test order search with no results"""
        test_email = "noorders@example.com"
        mock_response = {"success": True, "data": []}
        
        with patch.object(api_client, '_make_request') as mock_request:
            mock_request.return_value = mock_response
            
            result = await api_client.get_orders_by_email(test_email)
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_get_orders_by_email_api_error(self, api_client):
        """Test order search with API error"""
        test_email = "test@example.com"
        
        with patch.object(api_client, '_make_request') as mock_request:
            mock_request.side_effect = APIClientError("Server error", 500)
            
            with pytest.raises(APIClientError):
                await api_client.get_orders_by_email(test_email)


if __name__ == "__main__":
    pytest.main([__file__])