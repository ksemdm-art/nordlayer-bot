"""
Error handling utilities for the Telegram bot.
"""
import logging
from typing import Optional
from telegram import Update
from telegram.ext import ContextTypes
from aiohttp import ClientResponseError, ClientError
from api_client import APIClientError

logger = logging.getLogger(__name__)


class BotErrorHandler:
    """Centralized error handling for the Telegram bot"""
    
    @staticmethod
    async def handle_api_error(
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        error: Exception,
        user_context: Optional[str] = None
    ):
        """
        Handle API-related errors with user-friendly messages
        
        Args:
            update: Telegram update object
            context: Bot context
            error: The exception that occurred
            user_context: Additional context about what the user was doing
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        action_context = f" while {user_context}" if user_context else ""
        
        # Default user message
        user_message = "Произошла ошибка при обращении к серверу. Попробуйте позже."
        
        # Handle specific error types
        if isinstance(error, APIClientError):
            if error.status_code:
                if error.status_code == 400:
                    user_message = "Некорректные данные. Проверьте введенную информацию."
                elif error.status_code == 404:
                    user_message = "Запрашиваемый ресурс не найден."
                elif error.status_code == 422:
                    user_message = "Ошибка валидации данных. Проверьте правильность заполнения."
                elif error.status_code >= 500:
                    user_message = "Сервер временно недоступен. Попробуйте позже."
            
            # Log detailed error for debugging
            logger.error(
                f"API Error for user {user_id}{action_context}: "
                f"Status {error.status_code}, Message: {error.message}"
            )
        
        elif isinstance(error, ClientResponseError):
            if error.status == 400:
                user_message = "Некорректные данные. Проверьте введенную информацию."
            elif error.status == 404:
                user_message = "Запрашиваемый ресурс не найден."
            elif error.status >= 500:
                user_message = "Сервер временно недоступен. Попробуйте позже."
            
            logger.error(
                f"HTTP Error for user {user_id}{action_context}: "
                f"Status {error.status}, Message: {error.message}"
            )
        
        elif isinstance(error, ClientError):
            user_message = "Проблема с подключением к серверу. Проверьте интернет-соединение."
            logger.error(f"Network Error for user {user_id}{action_context}: {error}")
        
        else:
            # Generic error
            logger.error(f"Unexpected Error for user {user_id}{action_context}: {error}")
        
        # Send user-friendly message
        try:
            if update.effective_message:
                await update.effective_message.reply_text(user_message)
            elif update.callback_query:
                await update.callback_query.message.reply_text(user_message)
        except Exception as send_error:
            logger.error(f"Failed to send error message to user {user_id}: {send_error}")
    
    @staticmethod
    async def handle_file_error(
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        error_type: str,
        filename: Optional[str] = None
    ):
        """
        Handle file-related errors with specific messages
        
        Args:
            update: Telegram update object
            context: Bot context
            error_type: Type of file error
            filename: Name of the file that caused the error
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        file_info = f" ({filename})" if filename else ""
        
        error_messages = {
            "file_too_large": f"Файл{file_info} слишком большой. Максимальный размер: 50MB",
            "invalid_format": f"Неподдерживаемый формат файла{file_info}. Используйте: .stl, .obj, .3mf",
            "upload_failed": f"Ошибка загрузки файла{file_info}. Попробуйте еще раз.",
            "file_not_found": "Файл не найден. Попробуйте отправить файл заново.",
            "file_corrupted": f"Файл{file_info} поврежден или не может быть обработан.",
            "download_failed": f"Не удалось скачать файл{file_info} из Telegram."
        }
        
        message = error_messages.get(error_type, f"Ошибка обработки файла{file_info}")
        
        # Log the error
        logger.error(f"File Error for user {user_id}: {error_type}{file_info}")
        
        # Send message to user
        try:
            await update.effective_message.reply_text(message)
        except Exception as send_error:
            logger.error(f"Failed to send file error message to user {user_id}: {send_error}")
    
    @staticmethod
    async def handle_validation_error(
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        field_name: str,
        error_message: Optional[str] = None
    ):
        """
        Handle validation errors for user input
        
        Args:
            update: Telegram update object
            context: Bot context
            field_name: Name of the field that failed validation
            error_message: Custom error message
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        
        default_messages = {
            "email": "Некорректный email адрес. Пример: user@example.com",
            "phone": "Некорректный номер телефона. Пример: +7 900 123-45-67",
            "name": "Имя должно содержать только буквы и быть длиной от 2 до 50 символов",
            "service": "Выберите услугу из предложенного списка",
            "specifications": "Некорректные параметры заказа"
        }
        
        message = error_message or default_messages.get(
            field_name, 
            f"Некорректное значение для поля '{field_name}'"
        )
        
        # Log validation error
        logger.warning(f"Validation Error for user {user_id}: {field_name} - {message}")
        
        # Send message to user
        try:
            await update.effective_message.reply_text(f"❌ {message}")
        except Exception as send_error:
            logger.error(f"Failed to send validation error message to user {user_id}: {send_error}")
    
    @staticmethod
    async def handle_session_error(
        update: Update, 
        context: ContextTypes.DEFAULT_TYPE, 
        error_type: str
    ):
        """
        Handle session-related errors
        
        Args:
            update: Telegram update object
            context: Bot context
            error_type: Type of session error
        """
        user_id = update.effective_user.id if update.effective_user else "unknown"
        
        error_messages = {
            "session_not_found": "Сессия не найдена. Начните заново с команды /start",
            "session_expired": "Сессия истекла. Начните заново с команды /start",
            "invalid_step": "Неверный шаг в процессе заказа. Начните заново с команды /order",
            "session_corrupted": "Данные сессии повреждены. Начните заново с команды /start"
        }
        
        message = error_messages.get(error_type, "Ошибка сессии. Начните заново с команды /start")
        
        # Log session error
        logger.error(f"Session Error for user {user_id}: {error_type}")
        
        # Send message to user
        try:
            await update.effective_message.reply_text(f"⚠️ {message}")
        except Exception as send_error:
            logger.error(f"Failed to send session error message to user {user_id}: {send_error}")
    
    @staticmethod
    def log_user_action(user_id: int, action: str, details: Optional[str] = None):
        """
        Log user actions for analytics and debugging
        
        Args:
            user_id: Telegram user ID
            action: Action performed by user
            details: Additional details about the action
        """
        detail_info = f" - {details}" if details else ""
        logger.info(f"User {user_id} action: {action}{detail_info}")
    
    @staticmethod
    def log_system_event(event: str, details: Optional[str] = None):
        """
        Log system events
        
        Args:
            event: System event name
            details: Additional details about the event
        """
        detail_info = f" - {details}" if details else ""
        logger.info(f"System event: {event}{detail_info}")