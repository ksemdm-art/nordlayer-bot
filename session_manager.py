"""
Session management for Telegram bot user states and order processing.
"""
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any
import json
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderStep(Enum):
    """Enumeration of order processing steps"""
    START = "start"
    SERVICE_SELECTION = "service_selection"
    CONTACT_INFO = "contact_info"
    FILE_UPLOAD = "file_upload"
    SPECIFICATIONS = "specifications"
    DELIVERY = "delivery"
    CONFIRMATION = "confirmation"
    COMPLETED = "completed"


@dataclass
class OrderSession:
    """Data class for storing user order session state"""
    user_id: int
    step: OrderStep = OrderStep.START
    service_id: Optional[int] = None
    service_name: Optional[str] = None
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None
    files: List[Dict[str, Any]] = field(default_factory=list)
    specifications: Dict[str, Any] = field(default_factory=dict)
    delivery_needed: Optional[bool] = None
    delivery_details: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_order_data(self) -> Dict[str, Any]:
        """
        Convert session data to order creation format
        
        Returns:
            Dictionary suitable for API order creation
        """
        # Prepare specifications with all collected data
        specifications = {
            **self.specifications,
            "files_info": self.files,
            "order_source": "telegram_bot",
            "bot_user_id": self.user_id
        }
        
        # Add customer phone to specifications if provided (for backward compatibility)
        if self.customer_phone:
            specifications["customer_phone"] = self.customer_phone
        
        order_data = {
            "customer_name": self.customer_name,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "service_id": self.service_id,
            "source": "TELEGRAM",
            "specifications": specifications
        }
        
        # Add delivery information if needed
        if self.delivery_needed is not None:
            order_data["delivery_needed"] = "true" if self.delivery_needed else "false"
            if self.delivery_details:
                order_data["delivery_details"] = self.delivery_details
        
        # Add customer_contact for backward compatibility with legacy API
        order_data["customer_contact"] = self.customer_email
        
        return order_data
    
    def is_complete(self) -> bool:
        """Check if all required order information is collected"""
        required_fields = [
            self.customer_name,
            self.customer_email,
            self.service_id
        ]
        
        return all(field is not None for field in required_fields) and len(self.files) > 0
    
    def get_summary(self) -> str:
        """Get a formatted summary of the order session"""
        summary_lines = [
            "📋 Резюме заказа:",
            "",
            f"👤 Имя: {self.customer_name or 'Не указано'}",
            f"📧 Email: {self.customer_email or 'Не указан'}",
            f"📱 Телефон: {self.customer_phone or 'Не указан'}",
            f"🛍️ Услуга: {self.service_name or 'Не выбрана'}",
            f"📁 Файлов: {len(self.files)}",
        ]
        
        # Add specifications if any
        if self.specifications:
            summary_lines.append("")
            summary_lines.append("⚙️ Параметры:")
            for key, value in self.specifications.items():
                summary_lines.append(f"  • {key}: {value}")
        
        # Add delivery info
        if self.delivery_needed is not None:
            summary_lines.append("")
            if self.delivery_needed:
                summary_lines.append("🚚 Доставка: Требуется")
                if self.delivery_details:
                    summary_lines.append(f"📍 Адрес: {self.delivery_details}")
            else:
                summary_lines.append("🏪 Доставка: Самовывоз")
        
        return "\n".join(summary_lines)


class SessionManager:
    """Manager for user sessions and order states"""
    
    def __init__(self):
        self.sessions: Dict[int, OrderSession] = {}
        logger.info("SessionManager initialized")
    
    def get_session(self, user_id: int) -> Optional[OrderSession]:
        """
        Get existing session for user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            OrderSession if exists, None otherwise
        """
        return self.sessions.get(user_id)
    
    def create_session(self, user_id: int) -> OrderSession:
        """
        Create new session for user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            New OrderSession instance
        """
        session = OrderSession(user_id=user_id)
        self.sessions[user_id] = session
        logger.info(f"Created new session for user {user_id}")
        return session
    
    def get_or_create_session(self, user_id: int) -> OrderSession:
        """
        Get existing session or create new one
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            OrderSession instance
        """
        session = self.get_session(user_id)
        if session is None:
            session = self.create_session(user_id)
        return session
    
    def update_session(self, user_id: int, **kwargs) -> Optional[OrderSession]:
        """
        Update session data
        
        Args:
            user_id: Telegram user ID
            **kwargs: Fields to update
            
        Returns:
            Updated session or None if not found
        """
        session = self.get_session(user_id)
        if session:
            for key, value in kwargs.items():
                if hasattr(session, key):
                    setattr(session, key, value)
                    logger.debug(f"Updated session {user_id}: {key} = {value}")
                else:
                    logger.warning(f"Attempted to set unknown session field: {key}")
            return session
        return None
    
    def clear_session(self, user_id: int) -> bool:
        """
        Clear session for user
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            True if session was cleared, False if not found
        """
        if user_id in self.sessions:
            del self.sessions[user_id]
            logger.info(f"Cleared session for user {user_id}")
            return True
        return False
    
    def reset_session_step(self, user_id: int, step: OrderStep) -> Optional[OrderSession]:
        """
        Reset session to specific step
        
        Args:
            user_id: Telegram user ID
            step: Step to reset to
            
        Returns:
            Updated session or None if not found
        """
        session = self.get_session(user_id)
        if session:
            session.step = step
            logger.info(f"Reset session {user_id} to step {step.value}")
            return session
        return None
    
    def get_active_sessions_count(self) -> int:
        """Get count of active sessions"""
        return len(self.sessions)
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """
        Clean up old sessions
        
        Args:
            max_age_hours: Maximum age of sessions in hours
        """
        current_time = datetime.now()
        old_sessions = []
        
        for user_id, session in self.sessions.items():
            age_hours = (current_time - session.created_at).total_seconds() / 3600
            if age_hours > max_age_hours:
                old_sessions.append(user_id)
        
        for user_id in old_sessions:
            self.clear_session(user_id)
        
        if old_sessions:
            logger.info(f"Cleaned up {len(old_sessions)} old sessions")
    
    def export_session_data(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Export session data as dictionary (for debugging/logging)
        
        Args:
            user_id: Telegram user ID
            
        Returns:
            Session data dictionary or None
        """
        session = self.get_session(user_id)
        if session:
            return {
                "user_id": session.user_id,
                "step": session.step.value,
                "service_id": session.service_id,
                "service_name": session.service_name,
                "customer_name": session.customer_name,
                "customer_email": session.customer_email,
                "customer_phone": session.customer_phone,
                "files_count": len(session.files),
                "specifications": session.specifications,
                "delivery_needed": session.delivery_needed,
                "created_at": session.created_at.isoformat(),
                "is_complete": session.is_complete()
            }
        return None