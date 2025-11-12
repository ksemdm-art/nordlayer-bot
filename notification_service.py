"""
Notification service for sending alerts about orders and system events.
"""
import logging
from typing import List, Dict, Any, Optional
from telegram import Bot
from telegram.error import TelegramError

from config import settings
from subscription_manager import SubscriptionManager

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for sending notifications to administrators and users"""
    
    def __init__(self, bot_token: str, admin_chat_ids: List[int]):
        self.bot = Bot(token=bot_token)
        self.admin_chat_ids = admin_chat_ids
        self.subscription_manager = SubscriptionManager()
        logger.info(f"NotificationService initialized with {len(admin_chat_ids)} admin chats")
    
    async def notify_new_order(self, order_data: Dict[str, Any], user_id: int):
        """
        Notify administrators about a new order
        
        Args:
            order_data: Order information from API response
            user_id: Telegram user ID who created the order
        """
        try:
            order_id = order_data.get('id', 'неизвестен')
            customer_name = order_data.get('customer_name', 'Не указано')
            customer_email = order_data.get('customer_email', 'Не указан')
            customer_phone = order_data.get('customer_phone', 'Не указан')
            service_name = order_data.get('service_name', 'Не указана')
            total_price = order_data.get('total_price', 'Не рассчитана')
            
            # Extract specifications
            specs = order_data.get('specifications', {})
            files_count = len(specs.get('files_info', []))
            material = specs.get('material', 'Не указан')
            quality = specs.get('quality', 'Не указано')
            infill = specs.get('infill', 'Не указано')
            
            # Format delivery info
            delivery_needed = order_data.get('delivery_needed')
            delivery_info = "Самовывоз"
            if delivery_needed == "true":
                delivery_details = order_data.get('delivery_details', 'Адрес не указан')
                delivery_info = f"Доставка: {delivery_details}"
            
            message = (
                "🆕 **Новый заказ из Telegram бота!**\n\n"
                f"📋 **Заказ #{order_id}**\n"
                f"👤 Клиент: {customer_name}\n"
                f"📧 Email: {customer_email}\n"
                f"📱 Телефон: {customer_phone}\n"
                f"🛍️ Услуга: {service_name}\n"
                f"💰 Стоимость: {total_price}\n\n"
                f"⚙️ **Параметры печати:**\n"
                f"🔹 Материал: {material}\n"
                f"🔹 Качество: {quality}\n"
                f"🔹 Заполнение: {infill}%\n"
                f"📁 Файлов: {files_count}\n\n"
                f"🚚 **Доставка:** {delivery_info}\n\n"
                f"🤖 Источник: Telegram Bot (User ID: {user_id})\n"
                f"⏰ Требует обработки в админ-панели"
            )
            
            # Send to all admin chats
            for admin_id in self.admin_chat_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id, 
                        text=message,
                        parse_mode='Markdown'
                    )
                    logger.info(f"New order notification sent to admin {admin_id}")
                except TelegramError as e:
                    logger.error(f"Failed to notify admin {admin_id} about new order: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error notifying admin {admin_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in notify_new_order: {e}")
    
    async def notify_status_change(self, user_id: int, order_data: Dict[str, Any]):
        """
        Notify user about order status change
        
        Args:
            user_id: Telegram user ID to notify
            order_data: Updated order information
        """
        try:
            # Check if user is subscribed to status change notifications
            if not self.subscription_manager.is_subscribed(user_id, "status_change"):
                logger.debug(f"User {user_id} is not subscribed to status change notifications")
                return
            
            order_id = order_data.get('id', 'неизвестен')
            status = order_data.get('status', 'unknown')
            
            status_messages = {
                "confirmed": "✅ Ваш заказ подтвержден и принят в работу",
                "in_progress": "🔄 Ваш заказ выполняется",
                "ready": "🎉 Ваш заказ готов к получению!",
                "completed": "✅ Заказ завершен. Спасибо за обращение!",
                "cancelled": "❌ Заказ отменен"
            }
            
            status_message = status_messages.get(status, f"Статус заказа изменен: {status}")
            
            message = (
                f"📦 **Заказ #{order_id}**\n"
                f"{status_message}\n\n"
                f"Для получения подробной информации используйте команду /track\n\n"
                f"💡 Чтобы отписаться от уведомлений, используйте команду /unsubscribe"
            )
            
            await self.bot.send_message(
                chat_id=user_id, 
                text=message,
                parse_mode='Markdown'
            )
            
            logger.info(f"Status change notification sent to user {user_id} for order {order_id}")
            
        except TelegramError as e:
            logger.error(f"Failed to notify user {user_id} about status change: {e}")
        except Exception as e:
            logger.error(f"Unexpected error notifying user {user_id}: {e}")
    
    async def notify_status_change_by_email(self, email: str, order_data: Dict[str, Any]):
        """
        Notify all users subscribed to an email about order status change
        
        Args:
            email: Customer email address
            order_data: Updated order information
        """
        try:
            # Find all users subscribed to this email
            subscribed_users = self.subscription_manager.get_subscribed_users_by_email(email)
            
            if not subscribed_users:
                logger.debug(f"No users subscribed to notifications for email {email}")
                return
            
            # Send notification to all subscribed users
            for user_id in subscribed_users:
                await self.notify_status_change(user_id, order_data)
            
            logger.info(f"Status change notifications sent to {len(subscribed_users)} users for email {email}")
            
        except Exception as e:
            logger.error(f"Error notifying users for email {email}: {e}")
    
    async def notify_system_error(self, error_message: str, context: Optional[str] = None):
        """
        Notify administrators about system errors
        
        Args:
            error_message: Error description
            context: Additional context about the error
        """
        try:
            context_info = f"\n\n📍 Контекст: {context}" if context else ""
            
            message = (
                "⚠️ **Системная ошибка в Telegram боте**\n\n"
                f"❌ Ошибка: {error_message}"
                f"{context_info}\n\n"
                f"🔧 Требует внимания администратора"
            )
            
            # Send to all admin chats
            for admin_id in self.admin_chat_ids:
                try:
                    await self.bot.send_message(
                        chat_id=admin_id, 
                        text=message,
                        parse_mode='Markdown'
                    )
                except TelegramError as e:
                    logger.error(f"Failed to notify admin {admin_id} about system error: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error notifying admin {admin_id}: {e}")
        
        except Exception as e:
            logger.error(f"Error in notify_system_error: {e}")
    
    async def send_test_notification(self) -> bool:
        """
        Send test notification to verify service is working
        
        Returns:
            True if at least one notification was sent successfully
        """
        test_message = (
            "🧪 **Тестовое уведомление**\n\n"
            "Служба уведомлений Telegram бота работает корректно.\n"
            f"📊 Настроено {len(self.admin_chat_ids)} админ-чатов"
        )
        
        success_count = 0
        
        for admin_id in self.admin_chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=admin_id, 
                    text=test_message,
                    parse_mode='Markdown'
                )
                success_count += 1
                logger.info(f"Test notification sent to admin {admin_id}")
            except Exception as e:
                logger.error(f"Failed to send test notification to admin {admin_id}: {e}")
        
        return success_count > 0
    
    async def close(self):
        """Close the bot session"""
        try:
            # Note: Bot doesn't have a close method in python-telegram-bot v20+
            # The session is managed automatically
            pass
        except Exception as e:
            logger.error(f"Error closing notification service: {e}")