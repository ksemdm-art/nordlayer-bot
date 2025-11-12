"""
Order processing handlers for the Telegram bot.
Implements step-by-step order creation with state management.
"""
import logging
import re
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from session_manager import SessionManager, OrderSession, OrderStep
from api_client import APIClient, APIClientError
from error_handler import BotErrorHandler
from notification_service import NotificationService

logger = logging.getLogger(__name__)


class OrderHandlers:
    """Handlers for order processing workflow"""
    
    def __init__(self, api_client: APIClient, session_manager: SessionManager, notification_service: Optional[NotificationService] = None):
        self.api_client = api_client
        self.session_manager = session_manager
        self.notification_service = notification_service
    
    async def start_order_process(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the order process by showing service selection"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "start_order_process")
        
        try:
            # Create or reset session
            session = self.session_manager.create_session(user_id)
            session.step = OrderStep.SERVICE_SELECTION
            
            await self.show_service_selection(update, context)
            
        except Exception as e:
            await BotErrorHandler.handle_api_error(update, context, e, "starting order process")
    
    async def show_service_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show available services for selection"""
        user_id = update.effective_user.id
        
        try:
            # Fetch services from API
            services = await self.api_client.get_services(active_only=True)
            
            if not services:
                message = (
                    "❌ В данный момент услуги недоступны.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
                await self._send_or_edit_message(update, message)
                return
            
            # Build message
            message_lines = [
                "🛍️ Выберите услугу для заказа:",
                "",
                "Доступные услуги:"
            ]
            
            # Build keyboard with services
            keyboard = []
            for service in services:
                service_id = service.get('id')
                service_name = service.get('name', 'Услуга')
                if service_id:
                    # Truncate button text if too long
                    button_text = service_name if len(service_name) <= 30 else service_name[:27] + "..."
                    keyboard.append([InlineKeyboardButton(
                        f"🛍️ {button_text}", 
                        callback_data=f"order_select_service_{service_id}"
                    )])
            
            # Add cancel button
            keyboard.append([InlineKeyboardButton("❌ Отменить", callback_data="order_cancel")])
            
            message = "\n".join(message_lines)
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._send_or_edit_message(update, message, reply_markup)
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "fetching services for order")
        except Exception as e:
            logger.error(f"Unexpected error showing service selection: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "showing service selection")
    
    async def handle_service_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int):
        """Handle service selection and move to contact info"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "order_service_selection", f"service_id: {service_id}")
        
        try:
            session = self.session_manager.get_session(user_id)
            if not session:
                await BotErrorHandler.handle_session_error(update, context, "session_not_found")
                return
            
            # Fetch service details
            services = await self.api_client.get_services(active_only=True)
            selected_service = next((s for s in services if s.get('id') == service_id), None)
            
            if not selected_service:
                await update.callback_query.message.reply_text(
                    "❌ Услуга не найдена или недоступна.\n"
                    "Попробуйте выбрать другую услугу."
                )
                return
            
            # Update session
            session.service_id = service_id
            session.service_name = selected_service.get('name', 'Услуга')
            session.step = OrderStep.CONTACT_INFO
            
            # Show contact info collection
            await self.show_contact_info_collection(update, context)
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "selecting service")
        except Exception as e:
            logger.error(f"Unexpected error handling service selection: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "handling service selection")
    
    async def show_contact_info_collection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show contact information collection step"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session:
            await BotErrorHandler.handle_session_error(update, context, "session_not_found")
            return
        
        message = (
            f"👤 Контактная информация\n\n"
            f"Выбранная услуга: **{session.service_name}**\n\n"
            "Для оформления заказа мне нужна ваша контактная информация.\n"
            "Пожалуйста, введите ваше **полное имя**:"
        )
        
        # Build keyboard with navigation
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к услугам", callback_data="order_back_to_services")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_or_edit_message(update, message, reply_markup)
    
    def _validate_order_data(self, session: OrderSession) -> Optional[str]:
        """
        Validate order data before sending to API
        
        Args:
            session: Order session to validate
            
        Returns:
            Error message if validation fails, None if valid
        """
        # Check required fields
        if not session.customer_name or len(session.customer_name.strip()) < 2:
            return "Имя клиента должно содержать минимум 2 символа"
        
        if not session.customer_email or not self._validate_email(session.customer_email):
            return "Некорректный email адрес"
        
        if not session.service_id:
            return "Не выбрана услуга"
        
        if not session.files:
            return "Необходимо загрузить хотя бы один файл"
        
        # Validate phone if provided
        if session.customer_phone and not self._validate_phone(session.customer_phone):
            return "Некорректный номер телефона"
        
        # Validate specifications
        if not session.specifications:
            return "Не указаны параметры печати"
        
        required_specs = ['material', 'quality', 'infill']
        for spec in required_specs:
            if spec not in session.specifications:
                return f"Не указан параметр: {spec}"
        
        # Validate delivery info
        if session.delivery_needed is None:
            return "Не выбран способ получения заказа"
        
        if session.delivery_needed and not session.delivery_details:
            return "Не указан адрес доставки"
        
        return None
    
    async def _handle_order_creation_error(self, update: Update, context: ContextTypes.DEFAULT_TYPE, error: Exception):
        """
        Handle errors during order creation with user-friendly messages
        
        Args:
            update: Telegram update object
            context: Bot context
            error: The exception that occurred
        """
        user_id = update.effective_user.id
        
        # Determine user-friendly error message
        if isinstance(error, APIClientError):
            if error.status_code == 400:
                user_message = (
                    "❌ Ошибка в данных заказа.\n"
                    "Проверьте правильность заполнения всех полей и попробуйте снова."
                )
            elif error.status_code == 422:
                user_message = (
                    "❌ Ошибка валидации данных.\n"
                    "Некоторые поля заполнены некорректно. Проверьте данные и попробуйте снова."
                )
            elif error.status_code >= 500:
                user_message = (
                    "⚠️ Сервер временно недоступен.\n"
                    "Попробуйте создать заказ через несколько минут."
                )
            else:
                user_message = (
                    "❌ Не удалось создать заказ.\n"
                    "Попробуйте еще раз или обратитесь к администратору."
                )
        else:
            user_message = (
                "❌ Произошла неожиданная ошибка при создании заказа.\n"
                "Попробуйте еще раз или обратитесь к администратору."
            )
        
        # Add retry options
        keyboard = [
            [InlineKeyboardButton("🔄 Попробовать снова", callback_data="order_confirm")],
            [InlineKeyboardButton("✏️ Редактировать заказ", callback_data="order_edit_menu")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self._send_or_edit_message(update, user_message, reply_markup)
        except Exception as send_error:
            logger.error(f"Failed to send order creation error message to user {user_id}: {send_error}")
    
    def _validate_name(self, name: str) -> bool:
        """Validate customer name"""
        if not name or len(name.strip()) < 2:
            return False
        if len(name.strip()) > 50:
            return False
        # Allow letters, spaces, hyphens, apostrophes
        return bool(re.match(r"^[a-zA-Zа-яА-ЯёЁ\s\-']+$", name.strip()))
    
    def _validate_email(self, email: str) -> bool:
        """Validate email address"""
        if not email:
            return False
        # Basic email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))
    
    def _validate_phone(self, phone: str) -> bool:
        """Validate phone number"""
        if not phone:
            return True  # Phone is optional
        # Remove all non-digit characters except +
        cleaned = re.sub(r'[^\d+]', '', phone)
        # Check if it looks like a phone number
        return bool(re.match(r'^\+?[1-9]\d{6,14}$', cleaned))
    
    async def _send_or_edit_message(self, update: Update, text: str, reply_markup=None):
        """Send new message or edit existing one based on update type"""
        try:
            if update.callback_query:
                # Edit existing message
                await update.callback_query.edit_message_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                # Send new message
                await update.message.reply_text(
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Error sending/editing message: {e}")
            # Fallback: try to send as new message
            try:
                if update.effective_message:
                    await update.effective_message.reply_text(
                        text=text,
                        reply_markup=reply_markup,
                        parse_mode='Markdown'
                    )
            except Exception:
                pass  # Give up if both methods fail
    
    async def confirm_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Confirm and create the order"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.CONFIRMATION:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Validate order data before sending
        validation_error = self._validate_order_data(session)
        if validation_error:
            await BotErrorHandler.handle_validation_error(
                update, context, "order_data", validation_error
            )
            return
        
        if not session.is_complete():
            await update.callback_query.message.reply_text(
                "❌ Заказ не может быть создан. Не хватает обязательных данных.\n"
                "Пожалуйста, заполните все необходимые поля."
            )
            return
        
        try:
            # Show processing message
            processing_message = await update.callback_query.message.reply_text(
                "⏳ Создаем ваш заказ...\nПожалуйста, подождите."
            )
            
            # Create order via API
            order_data = session.to_order_data()
            logger.info(f"Creating order for user {user_id} with data: {order_data}")
            
            created_order = await self.api_client.create_order(order_data)
            
            # Extract order data from API response
            if isinstance(created_order, dict) and created_order.get('success'):
                order_info = created_order.get('data', {})
            else:
                order_info = created_order
            
            order_id = order_info.get('id', 'неизвестен')
            
            # Log successful order creation for analytics
            BotErrorHandler.log_system_event(
                "order_created", 
                f"user_id: {user_id}, order_id: {order_id}, service_id: {session.service_id}"
            )
            
            # Mark session as completed
            session.step = OrderStep.COMPLETED
            
            # Delete processing message
            try:
                await processing_message.delete()
            except Exception:
                pass  # Ignore if message can't be deleted
            
            # Success message with order details
            message = (
                "🎉 Заказ успешно создан!\n\n"
                f"📋 Номер заказа: **#{order_id}**\n"
                f"👤 Клиент: {session.customer_name}\n"
                f"📧 Email: {session.customer_email}\n"
                f"🛍️ Услуга: {session.service_name}\n"
                f"📁 Файлов: {len(session.files)}\n\n"
                "✅ **Следующие шаги:**\n"
                "1. Мы обработаем ваш заказ в течение 24 часов\n"
                "2. Свяжемся с вами для уточнения деталей\n"
                "3. Сообщим точные сроки и стоимость\n\n"
                "📧 Подтверждение отправлено на ваш email\n"
                "🔔 Используйте /track для отслеживания статуса"
            )
            
            keyboard = [
                [InlineKeyboardButton("📦 Отследить заказ", callback_data="track_order")],
                [InlineKeyboardButton("🛍️ Создать новый заказ", callback_data="start_order")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_or_edit_message(update, message, reply_markup)
            
            # Send notification to administrators about new order
            if self.notification_service:
                try:
                    await self.notification_service.notify_new_order(order_info, user_id)
                except Exception as notify_error:
                    logger.error(f"Failed to send admin notification for order {order_id}: {notify_error}")
            
            # Clear session after successful order creation
            self.session_manager.clear_session(user_id)
            logger.info(f"Order creation completed and session cleared for user {user_id}")
            
        except APIClientError as e:
            logger.error(f"API error creating order for user {user_id}: {e}")
            await self._handle_order_creation_error(update, context, e)
        except Exception as e:
            logger.error(f"Unexpected error creating order for user {user_id}: {e}")
            await self._handle_order_creation_error(update, context, e)