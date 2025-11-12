"""
Integration tests for the complete order creation flow from service selection to order creation.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from telegram import Update, User, Message, CallbackQuery, Document
from telegram.ext import ContextTypes

from session_manager import SessionManager, OrderSession, OrderStep
from api_client import APIClient, APIClientError
from order_handlers import OrderHandlers
from notification_service import NotificationService

# Configure pytest-asyncio
pytest_plugins = ('pytest_asyncio',)


class TestOrderIntegration:
    """Integration tests for complete order flow"""
    
    @pytest.fixture
    def mock_api_client(self):
        """Mock API client with typical responses"""
        api_client = AsyncMock(spec=APIClient)
        
        # Mock services response
        api_client.get_services.return_value = [
            {
                "id": 1,
                "name": "FDM печать",
                "description": "Стандартная 3D печать пластиком",
                "category": "printing"
            },
            {
                "id": 2,
                "name": "SLA печать",
                "description": "Высокоточная печать смолой",
                "category": "printing"
            }
        ]
        
        # Mock file upload response
        api_client.upload_file.return_value = {
            "success": True,
            "file_id": "test_file_123",
            "file_url": "/uploads/test_file_123.stl"
        }
        
        # Mock order creation response
        api_client.create_order.return_value = {
            "success": True,
            "data": {
                "id": 42,
                "customer_name": "Тест Тестов",
                "customer_email": "test@example.com",
                "service_name": "FDM печать",
                "status": "new",
                "specifications": {
                    "material": "pla",
                    "quality": "standard",
                    "infill": "30"
                }
            }
        }
        
        return api_client
    
    @pytest.fixture
    def session_manager(self):
        """Session manager instance"""
        return SessionManager()
    
    @pytest.fixture
    def mock_notification_service(self):
        """Mock notification service"""
        return AsyncMock(spec=NotificationService)
    
    @pytest.fixture
    def order_handlers(self, mock_api_client, session_manager, mock_notification_service):
        """Order handlers with mocked dependencies"""
        return OrderHandlers(mock_api_client, session_manager, mock_notification_service)
    
    @pytest.fixture
    def mock_update(self):
        """Mock Telegram update object"""
        update = MagicMock(spec=Update)
        update.effective_user = MagicMock(spec=User)
        update.effective_user.id = 12345
        update.effective_user.first_name = "Тест"
        update.callback_query = MagicMock(spec=CallbackQuery)
        update.callback_query.message = MagicMock(spec=Message)
        update.callback_query.edit_message_text = AsyncMock()
        update.callback_query.message.reply_text = AsyncMock()
        update.message = MagicMock(spec=Message)
        update.message.reply_text = AsyncMock()
        update.effective_message = MagicMock(spec=Message)
        update.effective_message.reply_text = AsyncMock()
        return update
    
    @pytest.fixture
    def mock_context(self):
        """Mock Telegram context"""
        context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
        context.bot = MagicMock()
        context.bot.get_file = AsyncMock()
        return context
    
    @pytest.mark.asyncio
    async def test_complete_order_flow_success(self, order_handlers, mock_update, mock_context, mock_api_client, mock_notification_service):
        """Test complete successful order flow from start to finish"""
        user_id = 12345
        
        # Step 1: Start order process
        await order_handlers.start_order_process(mock_update, mock_context)
        
        # Verify session was created
        session = order_handlers.session_manager.get_session(user_id)
        assert session is not None
        assert session.step == OrderStep.SERVICE_SELECTION
        
        # Step 2: Select service
        await order_handlers.handle_service_selection(mock_update, mock_context, service_id=1)
        
        # Verify service was selected
        session = order_handlers.session_manager.get_session(user_id)
        assert session.service_id == 1
        assert session.service_name == "FDM печать"
        assert session.step == OrderStep.CONTACT_INFO
        
        # Step 3: Enter contact information
        await order_handlers.handle_contact_name(mock_update, mock_context, "Тест Тестов")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.customer_name == "Тест Тестов"
        
        await order_handlers.handle_contact_email(mock_update, mock_context, "test@example.com")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.customer_email == "test@example.com"
        
        await order_handlers.handle_contact_phone(mock_update, mock_context, "+7 900 123-45-67")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.customer_phone == "+7 900 123-45-67"
        assert session.step == OrderStep.FILE_UPLOAD
        
        # Step 4: Upload file
        mock_file = MagicMock(spec=Document)
        mock_file.file_name = "test_model.stl"
        mock_file.file_size = 1024 * 1024  # 1MB
        mock_file.file_id = "telegram_file_123"
        mock_file.mime_type = "application/octet-stream"
        
        mock_update.message.document = mock_file
        mock_context.bot.get_file.return_value.download_as_bytearray = AsyncMock(return_value=b"fake_stl_data")
        
        await order_handlers.handle_file_upload(mock_update, mock_context)
        
        # Verify file was uploaded
        session = order_handlers.session_manager.get_session(user_id)
        assert len(session.files) == 1
        assert session.files[0]["filename"] == "test_model.stl"
        mock_api_client.upload_file.assert_called_once()
        
        # Step 5: Continue to specifications
        await order_handlers.continue_with_files(mock_update, mock_context)
        session = order_handlers.session_manager.get_session(user_id)
        assert session.step == OrderStep.SPECIFICATIONS
        
        # Step 6: Select specifications
        await order_handlers.handle_material_selection(mock_update, mock_context, "pla")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.specifications["material"] == "pla"
        
        await order_handlers.handle_quality_selection(mock_update, mock_context, "standard")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.specifications["quality"] == "standard"
        
        await order_handlers.handle_infill_selection(mock_update, mock_context, "30")
        session = order_handlers.session_manager.get_session(user_id)
        assert session.specifications["infill"] == "30"
        assert session.step == OrderStep.DELIVERY
        
        # Step 7: Select delivery
        await order_handlers.handle_delivery_pickup(mock_update, mock_context)
        session = order_handlers.session_manager.get_session(user_id)
        assert session.delivery_needed == False
        assert session.step == OrderStep.CONFIRMATION
        
        # Step 8: Confirm order
        await order_handlers.confirm_order(mock_update, mock_context)
        
        # Verify order was created
        mock_api_client.create_order.assert_called_once()
        
        # Verify order data format
        call_args = mock_api_client.create_order.call_args[0][0]
        assert call_args["customer_name"] == "Тест Тестов"
        assert call_args["customer_email"] == "test@example.com"
        assert call_args["customer_phone"] == "+7 900 123-45-67"
        assert call_args["service_id"] == 1
        assert call_args["source"] == "TELEGRAM"
        assert call_args["delivery_needed"] == "false"
        assert "specifications" in call_args
        assert call_args["specifications"]["material"] == "pla"
        assert call_args["specifications"]["quality"] == "standard"
        assert call_args["specifications"]["infill"] == "30"
        assert len(call_args["specifications"]["files_info"]) == 1
        
        # Verify notification was sent
        mock_notification_service.notify_new_order.assert_called_once()
        
        # Verify session was cleared
        session = order_handlers.session_manager.get_session(user_id)
        assert session is None
    
    @pytest.mark.asyncio
    async def test_order_creation_api_error_handling(self, order_handlers, mock_update, mock_context, mock_api_client):
        """Test error handling during order creation"""
        user_id = 12345
        
        # Create a complete session
        session = order_handlers.session_manager.create_session(user_id)
        session.step = OrderStep.CONFIRMATION
        session.service_id = 1
        session.service_name = "FDM печать"
        session.customer_name = "Тест Тестов"
        session.customer_email = "test@example.com"
        session.files = [{"filename": "test.stl", "size": 1024}]
        session.specifications = {"material": "pla", "quality": "standard", "infill": "30"}
        session.delivery_needed = False
        
        # Mock API error
        mock_api_client.create_order.side_effect = APIClientError("Server error", status_code=500)
        
        # Attempt to confirm order
        await order_handlers.confirm_order(mock_update, mock_context)
        
        # Verify error was handled gracefully
        mock_update.callback_query.edit_message_text.assert_called()
        
        # Verify session was not cleared (user can retry)
        session = order_handlers.session_manager.get_session(user_id)
        assert session is not None
        assert session.step == OrderStep.CONFIRMATION
    
    @pytest.mark.asyncio
    async def test_order_data_validation(self, order_handlers, mock_update, mock_context):
        """Test order data validation before API call"""
        user_id = 12345
        
        # Create incomplete session
        session = order_handlers.session_manager.create_session(user_id)
        session.step = OrderStep.CONFIRMATION
        session.service_id = 1
        session.customer_name = "T"  # Too short
        session.customer_email = "invalid-email"  # Invalid format
        # Missing files and specifications
        
        # Attempt to confirm order
        await order_handlers.confirm_order(mock_update, mock_context)
        
        # Verify validation error was shown (check effective_message since that's what error handler uses)
        mock_update.effective_message.reply_text.assert_called()
        
        # Verify session was not cleared
        session = order_handlers.session_manager.get_session(user_id)
        assert session is not None
    
    @pytest.mark.asyncio
    async def test_session_to_order_data_conversion(self, session_manager):
        """Test conversion of session data to API order format"""
        user_id = 12345
        session = session_manager.create_session(user_id)
        
        # Fill session with test data
        session.service_id = 1
        session.customer_name = "Тест Тестов"
        session.customer_email = "test@example.com"
        session.customer_phone = "+7 900 123-45-67"
        session.files = [
            {"filename": "model1.stl", "size": 1024, "upload_result": {"file_id": "123"}},
            {"filename": "model2.stl", "size": 2048, "upload_result": {"file_id": "456"}}
        ]
        session.specifications = {
            "material": "pla",
            "quality": "high",
            "infill": "50"
        }
        session.delivery_needed = True
        session.delivery_details = "ул. Тестовая, д. 1, кв. 1"
        
        # Convert to order data
        order_data = session.to_order_data()
        
        # Verify required fields
        assert order_data["customer_name"] == "Тест Тестов"
        assert order_data["customer_email"] == "test@example.com"
        assert order_data["customer_phone"] == "+7 900 123-45-67"
        assert order_data["service_id"] == 1
        assert order_data["source"] == "TELEGRAM"
        assert order_data["delivery_needed"] == "true"
        assert order_data["delivery_details"] == "ул. Тестовая, д. 1, кв. 1"
        
        # Verify specifications
        specs = order_data["specifications"]
        assert specs["material"] == "pla"
        assert specs["quality"] == "high"
        assert specs["infill"] == "50"
        assert len(specs["files_info"]) == 2
        assert specs["order_source"] == "telegram_bot"
        assert specs["bot_user_id"] == user_id
        
        # Verify backward compatibility
        assert order_data["customer_contact"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_file_upload_validation(self, order_handlers, mock_update, mock_context):
        """Test file upload validation"""
        user_id = 12345
        
        # Create session in file upload step
        session = order_handlers.session_manager.create_session(user_id)
        session.step = OrderStep.FILE_UPLOAD
        session.service_id = 1
        session.customer_name = "Тест Тестов"
        session.customer_email = "test@example.com"
        
        # Test invalid file format
        mock_file = MagicMock(spec=Document)
        mock_file.file_name = "test_model.txt"  # Invalid format
        mock_file.file_size = 1024
        mock_update.message.document = mock_file
        
        await order_handlers.handle_file_upload(mock_update, mock_context)
        
        # Verify error message was sent
        mock_update.message.reply_text.assert_called()
        
        # Verify file was not added to session
        session = order_handlers.session_manager.get_session(user_id)
        assert len(session.files) == 0
        
        # Test file too large
        mock_file.file_name = "test_model.stl"  # Valid format
        mock_file.file_size = 60 * 1024 * 1024  # 60MB - too large
        
        await order_handlers.handle_file_upload(mock_update, mock_context)
        
        # Verify error message was sent
        assert mock_update.message.reply_text.call_count >= 2
        
        # Verify file was not added to session
        session = order_handlers.session_manager.get_session(user_id)
        assert len(session.files) == 0
    
    @pytest.mark.asyncio
    async def test_session_cleanup_after_successful_order(self, order_handlers, mock_update, mock_context, mock_api_client):
        """Test that session is properly cleaned up after successful order creation"""
        user_id = 12345
        
        # Create complete session
        session = order_handlers.session_manager.create_session(user_id)
        session.step = OrderStep.CONFIRMATION
        session.service_id = 1
        session.service_name = "FDM печать"
        session.customer_name = "Тест Тестов"
        session.customer_email = "test@example.com"
        session.files = [{"filename": "test.stl", "size": 1024}]
        session.specifications = {"material": "pla", "quality": "standard", "infill": "30"}
        session.delivery_needed = False
        
        # Confirm order
        await order_handlers.confirm_order(mock_update, mock_context)
        
        # Verify session was cleared
        session = order_handlers.session_manager.get_session(user_id)
        assert session is None
        
        # Verify order was created
        mock_api_client.create_order.assert_called_once()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])