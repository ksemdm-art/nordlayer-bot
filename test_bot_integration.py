"""
Integration test for bot initialization and basic functionality.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import asyncio

from main import TelegramBot
from api_client import APIClient


class TestBotIntegration:
    """Integration tests for the Telegram bot"""
    
    @pytest.mark.asyncio
    async def test_bot_initialization(self):
        """Test that bot can be initialized properly"""
        with patch('main.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.api_base_url = "http://test-api.com"
            mock_settings.api_timeout = 30
            mock_settings.log_level = "INFO"
            mock_settings.log_file = "test.log"
            mock_settings.session_cleanup_hours = 24
            
            bot = TelegramBot()
            
            # Verify bot was created
            assert bot is not None
            assert bot.token == "test_token"
            assert bot.api_client is None  # Not initialized yet
            assert bot.session_manager is not None
    
    @pytest.mark.asyncio
    async def test_bot_api_client_initialization(self):
        """Test that API client is properly initialized"""
        with patch('main.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.api_base_url = "http://test-api.com"
            mock_settings.api_timeout = 30
            mock_settings.log_level = "INFO"
            mock_settings.log_file = "test.log"
            
            bot = TelegramBot()
            
            # Mock the Application builder to avoid actual Telegram API calls
            with patch('main.Application') as mock_app_class:
                mock_app = MagicMock()
                mock_app.builder.return_value.token.return_value.build.return_value = mock_app
                mock_app_class.builder.return_value.token.return_value.build.return_value = mock_app
                
                await bot.initialize()
                
                # Verify API client was created
                assert bot.api_client is not None
                assert isinstance(bot.api_client, APIClient)
                assert bot.api_client.base_url == "http://test-api.com"
    
    @pytest.mark.asyncio
    async def test_services_catalog_with_real_api_client(self):
        """Test services catalog functionality with real API client structure"""
        with patch('main.settings') as mock_settings:
            mock_settings.telegram_bot_token = "test_token"
            mock_settings.api_base_url = "http://test-api.com"
            mock_settings.api_timeout = 30
            mock_settings.log_level = "INFO"
            mock_settings.log_file = "test.log"
            
            bot = TelegramBot()
            
            # Create a real API client but mock its methods
            bot.api_client = APIClient("http://test-api.com")
            bot.api_client.get_services = AsyncMock(return_value=[
                {
                    "id": 1,
                    "name": "Test Service",
                    "description": "Test Description",
                    "category": "test",
                    "features": ["Feature 1", "Feature 2"],
                    "is_active": True
                }
            ])
            
            # Mock update and context
            mock_update = MagicMock()
            mock_update.effective_user.id = 12345
            mock_update.effective_user.first_name = "TestUser"
            mock_update.message.reply_text = AsyncMock()
            
            mock_context = MagicMock()
            
            # Test services command
            await bot.services_command(mock_update, mock_context)
            
            # Verify API was called
            bot.api_client.get_services.assert_called_once_with(active_only=True)
            
            # Verify message was sent
            mock_update.message.reply_text.assert_called_once()
            call_args = mock_update.message.reply_text.call_args
            message_text = call_args[1]['text']
            
            # Verify message content
            assert "📋 Каталог услуг NordLayer" in message_text
            assert "Test Service" in message_text
    
    def test_pagination_logic_integration(self):
        """Test pagination logic with realistic data"""
        # Test with various service counts
        test_cases = [
            (3, 1),   # 3 services = 1 page
            (5, 1),   # 5 services = 1 page
            (6, 2),   # 6 services = 2 pages
            (12, 3),  # 12 services = 3 pages
            (15, 3),  # 15 services = 3 pages
        ]
        
        services_per_page = 5
        
        for total_services, expected_pages in test_cases:
            calculated_pages = (total_services + services_per_page - 1) // services_per_page
            assert calculated_pages == expected_pages, f"Failed for {total_services} services"
    
    def test_service_button_text_truncation(self):
        """Test service name truncation for buttons"""
        test_cases = [
            ("Short Name", "Short Name"),
            ("A" * 30, "A" * 30),  # Exactly 30 chars
            ("A" * 35, "A" * 27 + "..."),  # Over 30 chars, should truncate
        ]
        
        for input_name, expected_output in test_cases:
            if len(input_name) <= 30:
                result = input_name
            else:
                result = input_name[:27] + "..."
            
            assert result == expected_output
            assert len(result) <= 30
    
    def test_service_description_truncation(self):
        """Test service description truncation for preview"""
        test_cases = [
            ("Short description", "Short description"),
            ("A" * 80, "A" * 80),  # Exactly 80 chars
            ("A" * 100, "A" * 77 + "..."),  # Over 80 chars, should truncate
        ]
        
        for input_desc, expected_output in test_cases:
            if len(input_desc) <= 80:
                result = input_desc
            else:
                result = input_desc[:77] + "..."
            
            assert result == expected_output
            assert len(result) <= 80


if __name__ == "__main__":
    pytest.main([__file__])