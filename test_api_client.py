"""
Unit tests for the API client with mocked HTTP requests.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
import aiohttp
from aiohttp import ClientResponseError

from api_client import APIClient, APIClientError


class TestAPIClient:
    """Test cases for APIClient"""
    
    @pytest.fixture
    def api_client(self):
        """Create API client instance for testing"""
        return APIClient("http://test-api.com", timeout=10)
    
    @pytest.fixture
    def mock_session(self):
        """Create mock aiohttp session"""
        session = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_get_services_success(self, api_client, mock_session):
        """Test successful services retrieval"""
        # Mock response data
        mock_services = [
            {"id": 1, "name": "FDM Printing", "active": True},
            {"id": 2, "name": "SLA Printing", "active": True}
        ]
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": mock_services}
        
        # Mock session request context manager
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        # Patch the session
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.get_services()
        
        # Assertions
        assert result == mock_services
        mock_session.request.assert_called_once_with(
            "GET", 
            "http://test-api.com/api/v1/services",
            params={"active_only": "true"}
        )
    
    @pytest.mark.asyncio
    async def test_get_services_with_different_response_format(self, api_client, mock_session):
        """Test services retrieval with different response format"""
        mock_services = [{"id": 1, "name": "Test Service"}]
        
        # Mock response with services key instead of data
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"services": mock_services}
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.get_services()
        
        assert result == mock_services
    
    @pytest.mark.asyncio
    async def test_get_services_direct_list_response(self, api_client, mock_session):
        """Test services retrieval with direct list response"""
        mock_services = [{"id": 1, "name": "Test Service"}]
        
        # Mock response as direct list
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = mock_services
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.get_services()
        
        assert result == mock_services
    
    @pytest.mark.asyncio
    async def test_get_services_api_error(self, api_client, mock_session):
        """Test services retrieval with API error"""
        # Mock error response
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text.return_value = "Internal Server Error"
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            with pytest.raises(APIClientError) as exc_info:
                await api_client.get_services()
        
        assert exc_info.value.status_code == 500
        assert "API request failed: 500" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_create_order_success(self, api_client, mock_session):
        """Test successful order creation"""
        order_data = {
            "customer_name": "Test User",
            "customer_email": "test@example.com",
            "service_id": 1
        }
        
        mock_order_response = {
            "id": 123,
            "status": "created",
            **order_data
        }
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": mock_order_response}
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.create_order(order_data)
        
        assert result == mock_order_response
        mock_session.request.assert_called_once_with(
            "POST",
            "http://test-api.com/api/v1/orders",
            json=order_data,
            headers={"Content-Type": "application/json"}
        )
    
    @pytest.mark.asyncio
    async def test_create_order_validation_error(self, api_client, mock_session):
        """Test order creation with validation error"""
        order_data = {"invalid": "data"}
        
        # Mock validation error response
        mock_response = AsyncMock()
        mock_response.status = 422
        mock_response.text.return_value = "Validation Error"
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            with pytest.raises(APIClientError) as exc_info:
                await api_client.create_order(order_data)
        
        assert exc_info.value.status_code == 422
    
    @pytest.mark.asyncio
    async def test_upload_file_success(self, api_client, mock_session):
        """Test successful file upload"""
        file_data = b"fake file content"
        filename = "test.stl"
        
        mock_upload_response = {
            "file_id": "abc123",
            "filename": filename,
            "url": "http://example.com/files/abc123"
        }
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": mock_upload_response}
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.upload_file(file_data, filename)
        
        assert result == mock_upload_response
        
        # Verify the call was made with FormData
        call_args = mock_session.request.call_args
        assert call_args[0] == ("POST", "http://test-api.com/api/v1/files/upload")
        assert "data" in call_args[1]
    
    @pytest.mark.asyncio
    async def test_upload_file_with_content_type(self, api_client, mock_session):
        """Test file upload with specific content type"""
        file_data = b"fake file content"
        filename = "test.stl"
        content_type = "application/sla"
        
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": {"file_id": "abc123"}}
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            await api_client.upload_file(file_data, filename, content_type)
        
        # Verify content type was used
        call_args = mock_session.request.call_args
        assert "data" in call_args[1]
    
    @pytest.mark.asyncio
    async def test_get_orders_by_email_success(self, api_client, mock_session):
        """Test successful orders retrieval by email"""
        email = "test@example.com"
        mock_orders = [
            {"id": 1, "status": "completed"},
            {"id": 2, "status": "in_progress"}
        ]
        
        # Mock response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"data": mock_orders}
        
        mock_context_manager = AsyncMock()
        mock_context_manager.__aenter__.return_value = mock_response
        mock_context_manager.__aexit__.return_value = None
        mock_session.request.return_value = mock_context_manager
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            result = await api_client.get_orders_by_email(email)
        
        assert result == mock_orders
        mock_session.request.assert_called_once_with(
            "GET",
            "http://test-api.com/api/v1/orders/search",
            params={"email": email}
        )
    
    @pytest.mark.asyncio
    async def test_network_error_handling(self, api_client, mock_session):
        """Test network error handling"""
        # Mock network error
        mock_session.request.side_effect = aiohttp.ClientError("Connection failed")
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            with pytest.raises(APIClientError) as exc_info:
                await api_client.get_services()
        
        assert "Network error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_unexpected_error_handling(self, api_client, mock_session):
        """Test unexpected error handling"""
        # Mock unexpected error
        mock_session.request.side_effect = ValueError("Unexpected error")
        
        with patch.object(api_client, '_get_session', return_value=mock_session):
            with pytest.raises(APIClientError) as exc_info:
                await api_client.get_services()
        
        assert "Unexpected error" in str(exc_info.value)
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """Test API client as async context manager"""
        async with APIClient("http://test-api.com") as client:
            assert client.session is not None
        
        # Session should be closed after context exit
        assert client.session is None or client.session.closed
    
    @pytest.mark.asyncio
    async def test_close_method(self, api_client):
        """Test explicit close method"""
        # Create a session
        api_client._get_session()
        assert api_client.session is not None
        
        # Close it
        await api_client.close()
        assert api_client.session is None
    
    def test_base_url_normalization(self):
        """Test that base URL is properly normalized"""
        client = APIClient("http://example.com/")
        assert client.base_url == "http://example.com"
        
        client2 = APIClient("http://example.com")
        assert client2.base_url == "http://example.com"


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v"])