"""
Unit tests for the session manager and OrderSession.
"""
import pytest
from datetime import datetime, timedelta
from session_manager import SessionManager, OrderSession, OrderStep


class TestOrderSession:
    """Test cases for OrderSession dataclass"""
    
    def test_order_session_creation(self):
        """Test basic OrderSession creation"""
        session = OrderSession(user_id=123)
        
        assert session.user_id == 123
        assert session.step == OrderStep.START
        assert session.service_id is None
        assert session.files == []
        assert session.specifications == {}
        assert isinstance(session.created_at, datetime)
    
    def test_order_session_with_data(self):
        """Test OrderSession creation with initial data"""
        session = OrderSession(
            user_id=456,
            step=OrderStep.CONTACT_INFO,
            service_id=1,
            service_name="FDM Printing",
            customer_name="Test User",
            customer_email="test@example.com"
        )
        
        assert session.user_id == 456
        assert session.step == OrderStep.CONTACT_INFO
        assert session.service_id == 1
        assert session.service_name == "FDM Printing"
        assert session.customer_name == "Test User"
        assert session.customer_email == "test@example.com"
    
    def test_to_order_data_basic(self):
        """Test conversion to order data format"""
        session = OrderSession(
            user_id=123,
            customer_name="John Doe",
            customer_email="john@example.com",
            customer_phone="+1234567890",
            service_id=1
        )
        session.files = [{"filename": "test.stl", "file_id": "abc123"}]
        session.specifications = {"material": "PLA", "quality": "high"}
        
        order_data = session.to_order_data()
        
        expected = {
            "customer_name": "John Doe",
            "customer_email": "john@example.com",
            "customer_phone": "+1234567890",
            "service_id": 1,
            "source": "TELEGRAM",
            "specifications": {
                "material": "PLA",
                "quality": "high",
                "files_info": [{"filename": "test.stl", "file_id": "abc123"}]
            }
        }
        
        assert order_data == expected
    
    def test_to_order_data_with_delivery(self):
        """Test conversion to order data with delivery information"""
        session = OrderSession(
            user_id=123,
            customer_name="Jane Doe",
            customer_email="jane@example.com",
            service_id=2,
            delivery_needed=True,
            delivery_details="123 Main St, City"
        )
        session.files = [{"filename": "model.obj"}]
        
        order_data = session.to_order_data()
        
        assert order_data["delivery_needed"] == "true"
        assert order_data["delivery_details"] == "123 Main St, City"
    
    def test_to_order_data_no_delivery(self):
        """Test conversion to order data without delivery"""
        session = OrderSession(
            user_id=123,
            customer_name="Bob Smith",
            customer_email="bob@example.com",
            service_id=3,
            delivery_needed=False
        )
        session.files = [{"filename": "part.3mf"}]
        
        order_data = session.to_order_data()
        
        assert order_data["delivery_needed"] == "false"
        assert "delivery_details" not in order_data
    
    def test_is_complete_true(self):
        """Test is_complete returns True for complete session"""
        session = OrderSession(
            user_id=123,
            customer_name="Complete User",
            customer_email="complete@example.com",
            service_id=1
        )
        session.files = [{"filename": "complete.stl"}]
        
        assert session.is_complete() is True
    
    def test_is_complete_false_missing_name(self):
        """Test is_complete returns False when name is missing"""
        session = OrderSession(
            user_id=123,
            customer_email="incomplete@example.com",
            service_id=1
        )
        session.files = [{"filename": "file.stl"}]
        
        assert session.is_complete() is False
    
    def test_is_complete_false_missing_email(self):
        """Test is_complete returns False when email is missing"""
        session = OrderSession(
            user_id=123,
            customer_name="Incomplete User",
            service_id=1
        )
        session.files = [{"filename": "file.stl"}]
        
        assert session.is_complete() is False
    
    def test_is_complete_false_missing_service(self):
        """Test is_complete returns False when service is missing"""
        session = OrderSession(
            user_id=123,
            customer_name="Incomplete User",
            customer_email="incomplete@example.com"
        )
        session.files = [{"filename": "file.stl"}]
        
        assert session.is_complete() is False
    
    def test_is_complete_false_no_files(self):
        """Test is_complete returns False when no files"""
        session = OrderSession(
            user_id=123,
            customer_name="Incomplete User",
            customer_email="incomplete@example.com",
            service_id=1
        )
        
        assert session.is_complete() is False
    
    def test_get_summary_basic(self):
        """Test get_summary with basic information"""
        session = OrderSession(
            user_id=123,
            customer_name="Summary User",
            customer_email="summary@example.com",
            customer_phone="+1234567890",
            service_name="FDM Printing"
        )
        session.files = [{"filename": "test1.stl"}, {"filename": "test2.obj"}]
        
        summary = session.get_summary()
        
        assert "📋 Резюме заказа:" in summary
        assert "Summary User" in summary
        assert "summary@example.com" in summary
        assert "+1234567890" in summary
        assert "FDM Printing" in summary
        assert "Файлов: 2" in summary
    
    def test_get_summary_with_specifications(self):
        """Test get_summary with specifications"""
        session = OrderSession(user_id=123)
        session.specifications = {
            "material": "PLA",
            "quality": "high",
            "infill": "20%"
        }
        
        summary = session.get_summary()
        
        assert "⚙️ Параметры:" in summary
        assert "material: PLA" in summary
        assert "quality: high" in summary
        assert "infill: 20%" in summary
    
    def test_get_summary_with_delivery(self):
        """Test get_summary with delivery information"""
        session = OrderSession(
            user_id=123,
            delivery_needed=True,
            delivery_details="456 Oak Ave, Town"
        )
        
        summary = session.get_summary()
        
        assert "🚚 Доставка: Требуется" in summary
        assert "📍 Адрес: 456 Oak Ave, Town" in summary
    
    def test_get_summary_no_delivery(self):
        """Test get_summary without delivery"""
        session = OrderSession(
            user_id=123,
            delivery_needed=False
        )
        
        summary = session.get_summary()
        
        assert "🏪 Доставка: Самовывоз" in summary


class TestSessionManager:
    """Test cases for SessionManager"""
    
    @pytest.fixture
    def session_manager(self):
        """Create SessionManager instance for testing"""
        return SessionManager()
    
    def test_session_manager_creation(self, session_manager):
        """Test SessionManager initialization"""
        assert isinstance(session_manager.sessions, dict)
        assert len(session_manager.sessions) == 0
    
    def test_create_session(self, session_manager):
        """Test creating a new session"""
        user_id = 123
        session = session_manager.create_session(user_id)
        
        assert isinstance(session, OrderSession)
        assert session.user_id == user_id
        assert session.step == OrderStep.START
        assert user_id in session_manager.sessions
        assert session_manager.sessions[user_id] == session
    
    def test_get_session_existing(self, session_manager):
        """Test getting an existing session"""
        user_id = 456
        created_session = session_manager.create_session(user_id)
        retrieved_session = session_manager.get_session(user_id)
        
        assert retrieved_session == created_session
        assert retrieved_session.user_id == user_id
    
    def test_get_session_nonexistent(self, session_manager):
        """Test getting a non-existent session"""
        result = session_manager.get_session(999)
        assert result is None
    
    def test_get_or_create_session_existing(self, session_manager):
        """Test get_or_create with existing session"""
        user_id = 789
        created_session = session_manager.create_session(user_id)
        retrieved_session = session_manager.get_or_create_session(user_id)
        
        assert retrieved_session == created_session
        assert len(session_manager.sessions) == 1
    
    def test_get_or_create_session_new(self, session_manager):
        """Test get_or_create with new session"""
        user_id = 101112
        session = session_manager.get_or_create_session(user_id)
        
        assert isinstance(session, OrderSession)
        assert session.user_id == user_id
        assert user_id in session_manager.sessions
    
    def test_update_session_existing(self, session_manager):
        """Test updating an existing session"""
        user_id = 131415
        session_manager.create_session(user_id)
        
        updated_session = session_manager.update_session(
            user_id,
            step=OrderStep.CONTACT_INFO,
            customer_name="Updated Name",
            service_id=5
        )
        
        assert updated_session is not None
        assert updated_session.step == OrderStep.CONTACT_INFO
        assert updated_session.customer_name == "Updated Name"
        assert updated_session.service_id == 5
    
    def test_update_session_nonexistent(self, session_manager):
        """Test updating a non-existent session"""
        result = session_manager.update_session(999, customer_name="Test")
        assert result is None
    
    def test_update_session_invalid_field(self, session_manager):
        """Test updating session with invalid field"""
        user_id = 161718
        session_manager.create_session(user_id)
        
        # This should not raise an error, but should log a warning
        updated_session = session_manager.update_session(
            user_id,
            invalid_field="should be ignored",
            customer_name="Valid Name"
        )
        
        assert updated_session is not None
        assert updated_session.customer_name == "Valid Name"
        assert not hasattr(updated_session, 'invalid_field')
    
    def test_clear_session_existing(self, session_manager):
        """Test clearing an existing session"""
        user_id = 192021
        session_manager.create_session(user_id)
        
        assert user_id in session_manager.sessions
        
        result = session_manager.clear_session(user_id)
        
        assert result is True
        assert user_id not in session_manager.sessions
    
    def test_clear_session_nonexistent(self, session_manager):
        """Test clearing a non-existent session"""
        result = session_manager.clear_session(999)
        assert result is False
    
    def test_reset_session_step(self, session_manager):
        """Test resetting session step"""
        user_id = 222324
        session_manager.create_session(user_id)
        session_manager.update_session(user_id, step=OrderStep.CONFIRMATION)
        
        reset_session = session_manager.reset_session_step(user_id, OrderStep.CONTACT_INFO)
        
        assert reset_session is not None
        assert reset_session.step == OrderStep.CONTACT_INFO
    
    def test_reset_session_step_nonexistent(self, session_manager):
        """Test resetting step for non-existent session"""
        result = session_manager.reset_session_step(999, OrderStep.START)
        assert result is None
    
    def test_get_active_sessions_count(self, session_manager):
        """Test getting active sessions count"""
        assert session_manager.get_active_sessions_count() == 0
        
        session_manager.create_session(1)
        session_manager.create_session(2)
        session_manager.create_session(3)
        
        assert session_manager.get_active_sessions_count() == 3
        
        session_manager.clear_session(2)
        
        assert session_manager.get_active_sessions_count() == 2
    
    def test_cleanup_old_sessions(self, session_manager):
        """Test cleaning up old sessions"""
        # Create sessions with different ages
        old_time = datetime.now() - timedelta(hours=25)
        recent_time = datetime.now() - timedelta(hours=1)
        
        # Create old session
        old_session = session_manager.create_session(1)
        old_session.created_at = old_time
        
        # Create recent session
        recent_session = session_manager.create_session(2)
        recent_session.created_at = recent_time
        
        assert session_manager.get_active_sessions_count() == 2
        
        # Cleanup sessions older than 24 hours
        session_manager.cleanup_old_sessions(max_age_hours=24)
        
        # Only recent session should remain
        assert session_manager.get_active_sessions_count() == 1
        assert 1 not in session_manager.sessions
        assert 2 in session_manager.sessions
    
    def test_export_session_data(self, session_manager):
        """Test exporting session data"""
        user_id = 252627
        session = session_manager.create_session(user_id)
        session_manager.update_session(
            user_id,
            step=OrderStep.SPECIFICATIONS,
            customer_name="Export Test",
            customer_email="export@test.com",
            service_id=3
        )
        session.files = [{"filename": "export.stl"}]
        session.specifications = {"material": "ABS"}
        
        exported_data = session_manager.export_session_data(user_id)
        
        assert exported_data is not None
        assert exported_data["user_id"] == user_id
        assert exported_data["step"] == "specifications"
        assert exported_data["customer_name"] == "Export Test"
        assert exported_data["customer_email"] == "export@test.com"
        assert exported_data["service_id"] == 3
        assert exported_data["files_count"] == 1
        assert exported_data["specifications"] == {"material": "ABS"}
        assert "created_at" in exported_data
        assert "is_complete" in exported_data
    
    def test_export_session_data_nonexistent(self, session_manager):
        """Test exporting data for non-existent session"""
        result = session_manager.export_session_data(999)
        assert result is None


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])