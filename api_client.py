"""
API Client for interacting with the 3D printing platform backend.
"""
import logging
from typing import List, Dict, Any, Optional
import aiohttp
import aiofiles
from aiohttp import FormData, ClientResponseError

logger = logging.getLogger(__name__)


class APIClientError(Exception):
    """Base exception for API client errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class APIClient:
    """Client for interacting with the backend API"""
    
    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip('/')
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
    
    def _get_session(self) -> aiohttp.ClientSession:
        """Get or create session"""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self.session
    
    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request with error handling"""
        url = f"{self.base_url}{endpoint}"
        session = self._get_session()
        
        try:
            logger.info(f"Making {method} request to {url}")
            async with session.request(method, url, **kwargs) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    logger.error(f"API request failed: {response.status} - {error_text}")
                    raise APIClientError(
                        f"API request failed: {response.status}",
                        status_code=response.status
                    )
                
                content_type = response.headers.get('content-type', '')
                if 'application/json' in content_type:
                    return await response.json()
                else:
                    return {"data": await response.text()}
                    
        except aiohttp.ClientError as e:
            logger.error(f"Network error during API request: {e}")
            raise APIClientError(f"Network error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error during API request: {e}")
            raise APIClientError(f"Unexpected error: {str(e)}")
    
    async def get_services(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """
        Get list of available services
        
        Args:
            active_only: If True, return only active services
            
        Returns:
            List of service dictionaries
        """
        try:
            params = {"active_only": "true"} if active_only else {}
            response = await self._make_request("GET", "/api/v1/services", params=params)
            
            # Handle different response formats
            if isinstance(response, dict):
                return response.get("data", response.get("services", []))
            elif isinstance(response, list):
                return response
            else:
                logger.warning(f"Unexpected services response format: {type(response)}")
                return []
                
        except APIClientError:
            logger.error("Failed to fetch services from API")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching services: {e}")
            raise APIClientError(f"Failed to fetch services: {str(e)}")
    
    async def create_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new order
        
        Args:
            order_data: Order information dictionary
            
        Returns:
            Created order data with ID
        """
        try:
            logger.info(f"Creating order with data: {order_data}")
            response = await self._make_request(
                "POST", 
                "/api/v1/orders", 
                json=order_data,
                headers={"Content-Type": "application/json"}
            )
            
            # Extract order data from response
            if isinstance(response, dict):
                return response.get("data", response)
            else:
                return response
                
        except APIClientError:
            logger.error("Failed to create order via API")
            raise
        except Exception as e:
            logger.error(f"Unexpected error creating order: {e}")
            raise APIClientError(f"Failed to create order: {str(e)}")
    
    async def upload_file(self, file_data: bytes, filename: str, 
                         content_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload a file to the server
        
        Args:
            file_data: File content as bytes
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            Upload result with file URL/ID
        """
        try:
            # Create form data
            form_data = FormData()
            form_data.add_field(
                'file', 
                file_data, 
                filename=filename,
                content_type=content_type or 'application/octet-stream'
            )
            
            logger.info(f"Uploading file: {filename} ({len(file_data)} bytes)")
            response = await self._make_request(
                "POST", 
                "/api/v1/files/upload", 
                data=form_data
            )
            
            # Extract file data from response
            if isinstance(response, dict):
                return response.get("data", response)
            else:
                return response
                
        except APIClientError:
            logger.error(f"Failed to upload file {filename}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error uploading file {filename}: {e}")
            raise APIClientError(f"Failed to upload file: {str(e)}")
    
    async def get_orders_by_email(self, email: str) -> List[Dict[str, Any]]:
        """
        Get orders by customer email
        
        Args:
            email: Customer email address
            
        Returns:
            List of order dictionaries
        """
        try:
            params = {"email": email}
            response = await self._make_request("GET", "/api/v1/orders/search", params=params)
            
            # Handle different response formats
            if isinstance(response, dict):
                return response.get("data", response.get("orders", []))
            elif isinstance(response, list):
                return response
            else:
                logger.warning(f"Unexpected orders response format: {type(response)}")
                return []
                
        except APIClientError:
            logger.error(f"Failed to fetch orders for email {email}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching orders: {e}")
            raise APIClientError(f"Failed to fetch orders: {str(e)}")
    
    async def close(self):
        """Close the HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None