"""
Unit tests for services catalog functionality in Telegram bot.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, CallbackQuery, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from main import TelegramBot
from api_client import APIClient, APIClientError
from session_manager import SessionManager


class TestServicesCatalog:
    """Test cases for services catalog functionality"""
    
    @pytest.fixture
    def bot(self):
        """Create bot instance for testing"""
        with patch('main.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.api_base_url = "http://test-api.com"
            mock_settings.api_timeout = 30
            mock_settings.log_level = "INFO"
            mock_settings.log_file = "test.log"
            
            bot = TelegramBot()
            bot.api_client = AsyncMock(spec=APIClient)
            bot.session_manager = MagicMock(spec=SessionManager)
            return bot
    
    @pytest.fixture
    def mock_update(self):
        """Create mock update object"""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.first_name = "TestUser"
        update.message = MagicMock(spec=Message)
        update.callback_query = None
        return update
    
    @pytest.fixture
    def mock_callback_update(self):
        """Create mock callback query update"""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.first_name = "TestUser"
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.message = MagicMock(spec=Message)
        update.callback_query.edit_message_text = AsyncMock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Create mock context"""
        return MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    
    @pytest.fixture
    def sample_services(self):
        """Sample services data for testing"""
        return [
            {
                "id": 1,
                "name": "FDM 3D Печать",
                "description": "Высококачественная FDM печать пластиком PLA, ABS, PETG",
                "category": "3d_printing",
                "features": ["Быстрая печать", "Различные материалы", "Высокое качество"],
                "is_active": True
            },
            {
                "id": 2,
                "name": "SLA 3D Печать",
                "description": "Точная печать фотополимерной смолой для детализированных моделей",
                "category": "3d_printing",
                "features": ["Высокая точность", "Гладкая поверхность", "Мелкие детали"],
                "is_active": True
            },
            {
                "id": 3,
                "name": "Постобработка",
                "description": "Шлифовка, покраска и финишная обработка 3D моделей",
                "category": "post_processing",
                "features": ["Профессиональная покраска", "Шлифовка", "Сборка"],
                "is_active": True
            }
        ]
    
    @pytest.mark.asyncio
    async def test_services_command_success(self, bot, mock_update, mock_context, sample_services):
        """Test successful services command execution"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Mock message reply
        mock_update.message.reply_text = AsyncMock()
        
        # Execute command
        await bot.services_command(mock_update, mock_context)
        
        # Verify API was called
        bot.api_client.get_services.assert_called_once_with(active_only=True)
        
        # Verify message was sent
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        
        # Check message content
        message_text = call_args[1]['text']
        assert "📋 Каталог услуг NordLayer" in message_text
        assert "FDM 3D Печать" in message_text
        assert "SLA 3D Печать" in message_text
        
        # Check keyboard
        reply_markup = call_args[1]['reply_markup']
        assert isinstance(reply_markup, InlineKeyboardMarkup)
    
    @pytest.mark.asyncio
    async def test_services_command_empty_response(self, bot, mock_update, mock_context):
        """Test services command with empty services list"""
        # Mock empty API response
        bot.api_client.get_services.return_value = []
        
        # Mock message reply
        mock_update.message.reply_text = AsyncMock()
        
        # Execute command
        await bot.services_command(mock_update, mock_context)
        
        # Verify message was sent with appropriate content
        mock_update.message.reply_text.assert_called_once()
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[1]['text']
        assert "услуги недоступны" in message_text
    
    @pytest.mark.asyncio
    async def test_services_command_api_error(self, bot, mock_update, mock_context):
        """Test services command with API error"""
        # Mock API error
        bot.api_client.get_services.side_effect = APIClientError("API Error", 500)
        
        # Mock error handler
        with patch('main.BotErrorHandler.handle_api_error') as mock_error_handler:
            mock_error_handler.return_value = AsyncMock()
            
            # Execute command
            await bot.services_command(mock_update, mock_context)
            
            # Verify error handler was called
            mock_error_handler.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_show_services_catalog_pagination(self, bot, mock_update, mock_context):
        """Test services catalog with pagination"""
        # Create more services than fit on one page
        many_services = []
        for i in range(12):  # More than 5 services per page
            many_services.append({
                "id": i + 1,
                "name": f"Услуга {i + 1}",
                "description": f"Описание услуги {i + 1}",
                "category": "test",
                "is_active": True
            })
        
        bot.api_client.get_services.return_value = many_services
        mock_update.message.reply_text = AsyncMock()
        
        # Test first page
        await bot.show_services_catalog(mock_update, mock_context, page=0)
        
        call_args = mock_update.message.reply_text.call_args
        message_text = call_args[1]['text']
        reply_markup = call_args[1]['reply_markup']
        
        # Check pagination info
        assert "Страница 1 из 3" in message_text
        
        # Check that only first 5 services are shown
        assert "Услуга 1" in message_text
        assert "Услуга 5" in message_text
        assert "Услуга 6" not in message_text
        
        # Check pagination buttons exist
        keyboard = reply_markup.inline_keyboard
        pagination_buttons = [btn for row in keyboard for btn in row if "Вперёд" in btn.text or "Назад" in btn.text]
        assert len(pagination_buttons) > 0
    
    @pytest.mark.asyncio
    async def test_handle_service_selection_success(self, bot, mock_callback_update, mock_context, sample_services):
        """Test successful service selection"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Execute service selection
        await bot.handle_service_selection(mock_callback_update, mock_context, service_id=1)
        
        # Verify message was edited with service details
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_update.callback_query.edit_message_text.call_args
        
        message_text = call_args[1]['text']
        assert "FDM 3D Печать" in message_text
        assert "Высококачественная FDM печать" in message_text
        assert "Быстрая печать" in message_text
        
        # Check keyboard has order button
        reply_markup = call_args[1]['reply_markup']
        keyboard = reply_markup.inline_keyboard
        order_buttons = [btn for row in keyboard for btn in row if "Заказать" in btn.text]
        assert len(order_buttons) == 1
        assert "order_service_1" in order_buttons[0].callback_data
    
    @pytest.mark.asyncio
    async def test_handle_service_selection_not_found(self, bot, mock_callback_update, mock_context, sample_services):
        """Test service selection with non-existent service ID"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Mock reply_text for error message
        mock_callback_update.callback_query.message.reply_text = AsyncMock()
        
        # Execute service selection with non-existent ID
        await bot.handle_service_selection(mock_callback_update, mock_context, service_id=999)
        
        # Verify error message was sent
        mock_callback_update.callback_query.message.reply_text.assert_called_once()
        call_args = mock_callback_update.callback_query.message.reply_text.call_args
        message_text = call_args[0][0]
        assert "Услуга не найдена" in message_text
    
    @pytest.mark.asyncio
    async def test_callback_query_services_page(self, bot, mock_callback_update, mock_context, sample_services):
        """Test callback query for services pagination"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Mock callback query data
        mock_callback_update.callback_query.data = "services_page_1"
        mock_callback_update.callback_query.answer = AsyncMock()
        
        # Execute callback handler
        await bot.handle_callback_query(mock_callback_update, mock_context)
        
        # Verify callback was answered
        mock_callback_update.callback_query.answer.assert_called_once()
        
        # Verify API was called
        bot.api_client.get_services.assert_called_with(active_only=True)
    
    @pytest.mark.asyncio
    async def test_callback_query_select_service(self, bot, mock_callback_update, mock_context, sample_services):
        """Test callback query for service selection"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Mock callback query data
        mock_callback_update.callback_query.data = "select_service_2"
        mock_callback_update.callback_query.answer = AsyncMock()
        
        # Execute callback handler
        await bot.handle_callback_query(mock_callback_update, mock_context)
        
        # Verify callback was answered
        mock_callback_update.callback_query.answer.assert_called_once()
        
        # Verify service details were shown
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_update.callback_query.edit_message_text.call_args
        message_text = call_args[1]['text']
        assert "SLA 3D Печать" in message_text
    
    @pytest.mark.asyncio
    async def test_callback_query_show_services(self, bot, mock_callback_update, mock_context, sample_services):
        """Test callback query for showing services catalog"""
        # Mock API response
        bot.api_client.get_services.return_value = sample_services
        
        # Mock callback query data
        mock_callback_update.callback_query.data = "show_services"
        mock_callback_update.callback_query.answer = AsyncMock()
        
        # Execute callback handler
        await bot.handle_callback_query(mock_callback_update, mock_context)
        
        # Verify callback was answered
        mock_callback_update.callback_query.answer.assert_called_once()
        
        # Verify services catalog was shown
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_update.callback_query.edit_message_text.call_args
        message_text = call_args[1]['text']
        assert "📋 Каталог услуг NordLayer" in message_text
    
    @pytest.mark.asyncio
    async def test_callback_query_main_menu(self, bot, mock_callback_update, mock_context):
        """Test callback query for main menu"""
        # Mock callback query data
        mock_callback_update.callback_query.data = "main_menu"
        mock_callback_update.callback_query.answer = AsyncMock()
        
        # Execute callback handler
        await bot.handle_callback_query(mock_callback_update, mock_context)
        
        # Verify callback was answered
        mock_callback_update.callback_query.answer.assert_called_once()
        
        # Verify main menu was shown
        mock_callback_update.callback_query.edit_message_text.assert_called_once()
        call_args = mock_callback_update.callback_query.edit_message_text.call_args
        message_text = call_args[1]['text']
        assert "Добро пожаловать в NordLayer" in message_text
    
    @pytest.mark.asyncio
    async def test_send_or_edit_message_callback(self, bot, mock_callback_update):
        """Test _send_or_edit_message with callback query"""
        test_text = "Test message"
        test_markup = InlineKeyboardMarkup([[]])
        
        await bot._send_or_edit_message(mock_callback_update, test_text, test_markup)
        
        # Verify edit_message_text was called
        mock_callback_update.callback_query.edit_message_text.assert_called_once_with(
            text=test_text,
            reply_markup=test_markup,
            parse_mode='Markdown'
        )
    
    @pytest.mark.asyncio
    async def test_send_or_edit_message_regular(self, bot, mock_update):
        """Test _send_or_edit_message with regular message"""
        test_text = "Test message"
        test_markup = InlineKeyboardMarkup([[]])
        mock_update.message.reply_text = AsyncMock()
        
        await bot._send_or_edit_message(mock_update, test_text, test_markup)
        
        # Verify reply_text was called
        mock_update.message.reply_text.assert_called_once_with(
            text=test_text,
            reply_markup=test_markup,
            parse_mode='Markdown'
        )
    
    def test_service_data_formatting(self, sample_services):
        """Test service data formatting logic"""
        service = sample_services[0]
        
        # Test name extraction
        assert service.get('name') == "FDM 3D Печать"
        
        # Test description truncation logic
        long_description = "A" * 100
        truncated = long_description[:77] + "..." if len(long_description) > 80 else long_description
        assert len(truncated) <= 80
        
        # Test features formatting
        features = service.get('features', [])
        assert isinstance(features, list)
        assert len(features) > 0
    
    def test_pagination_logic(self):
        """Test pagination calculation logic"""
        services_per_page = 5
        
        # Test with 12 services
        total_services = 12
        total_pages = (total_services + services_per_page - 1) // services_per_page
        assert total_pages == 3
        
        # Test page 0
        page = 0
        start_idx = page * services_per_page
        end_idx = min(start_idx + services_per_page, total_services)
        assert start_idx == 0
        assert end_idx == 5
        
        # Test page 2 (last page)
        page = 2
        start_idx = page * services_per_page
        end_idx = min(start_idx + services_per_page, total_services)
        assert start_idx == 10
        assert end_idx == 12


if __name__ == "__main__":
    pytest.main([__file__])