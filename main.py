"""
Main Telegram bot application with API integration and session management.
Enhanced with graceful shutdown, production logging, and monitoring.
"""
import asyncio
import logging
import signal
import sys
import os
from typing import Optional, List, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters, 
    ContextTypes
)

from config import settings
from api_client import APIClient, APIClientError
from session_manager import SessionManager, OrderStep
from error_handler import BotErrorHandler
from health_check import HealthCheckServer
from order_handlers import OrderHandlers
from notification_service import NotificationService
from logging_config import setup_logging, get_logger_with_context, log_user_action
from webhook_handler import WebhookHandler

# Setup enhanced logging
setup_logging()
logger = logging.getLogger(__name__)


class TelegramBot:
    """Main Telegram bot class with API integration"""
    
    def __init__(self):
        self.token = settings.telegram_bot_token
        self.api_client: Optional[APIClient] = None
        self.session_manager = SessionManager()
        self.order_handlers: Optional[OrderHandlers] = None
        self.notification_service: Optional[NotificationService] = None
        self.webhook_handler: Optional[WebhookHandler] = None
        self.application: Optional[Application] = None
        self.health_server = HealthCheckServer()
        self.health_runner = None
        self.webhook_runner = None
        self._shutdown_event = asyncio.Event()
        
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")
        
        logger.info("TelegramBot initialized")
    
    async def initialize(self):
        """Initialize bot components"""
        # Initialize API client
        self.api_client = APIClient(
            base_url=settings.api_base_url,
            timeout=settings.api_timeout
        )
        
        # Initialize notification service
        if settings.admin_chat_ids_list:
            self.notification_service = NotificationService(
                bot_token=self.token,
                admin_chat_ids=settings.admin_chat_ids_list
            )
            
            # Initialize webhook handler
            self.webhook_handler = WebhookHandler(self.notification_service)
        
        # Initialize order handlers
        self.order_handlers = OrderHandlers(
            self.api_client, 
            self.session_manager,
            self.notification_service
        )
        
        # Initialize Telegram application
        self.application = Application.builder().token(self.token).build()
        self._setup_handlers()
        
        logger.info("Bot components initialized")
    
    def _setup_handlers(self):
        """Setup command and message handlers"""
        if not self.application:
            return
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("services", self.services_command))
        self.application.add_handler(CommandHandler("order", self.order_command))
        self.application.add_handler(CommandHandler("track", self.track_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("cancel", self.cancel_command))
        
        # Callback query handler for inline keyboards
        self.application.add_handler(CallbackQueryHandler(self.handle_callback_query))
        
        # Message handlers
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text_message))
        self.application.add_handler(MessageHandler(filters.Document.ALL, self.handle_file))
        
        # Error handler
        self.application.add_error_handler(self.error_handler)
        
        logger.info("Bot handlers configured")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user_id = update.effective_user.id
        user_name = update.effective_user.first_name or "пользователь"
        
        BotErrorHandler.log_user_action(user_id, "start_command")
        
        # Create inline keyboard
        keyboard = [
            [InlineKeyboardButton("🛍️ Оформить заказ", callback_data="start_order")],
            [InlineKeyboardButton("📋 Наши услуги", callback_data="show_services")],
            [InlineKeyboardButton("📦 Отследить заказ", callback_data="track_order")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Добро пожаловать в NordLayer, {user_name}! 🖨️\n\n"
            "Мастерская цифрового ремесла из Карелии.\n"
            "Слой за слоем рождается форма.\n\n"
            "Здесь вы можете:\n"
            "• Оформить заказ на 3D печать\n"
            "• Посмотреть наши услуги\n"
            "• Отследить статус заказа\n\n"
            "Выберите действие:"
        )
        
        await update.message.reply_text(welcome_text, reply_markup=reply_markup)
    
    async def services_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /services command - show catalog of services"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "services_command")
        
        await self.show_services_catalog(update, context, page=0)
    
    async def order_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /order command - start order process"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "order_command")
        
        if not self.order_handlers:
            await update.message.reply_text("⚠️ Система заказов временно недоступна.")
            return
        
        await self.order_handlers.start_order_process(update, context)
    
    async def track_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /track command - track orders by email"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "track_command")
        
        await self.start_order_tracking(update, context)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "help_command")
        
        help_message = (
            "🔧 Помощь по использованию бота NordLayer:\n\n"
            "📋 Основные команды:\n"
            "/start - Главное меню\n"
            "/services - Список услуг\n"
            "/order - Оформить заказ\n"
            "/track - Отследить заказ\n"
            "/subscribe - Подписаться на уведомления\n"
            "/unsubscribe - Отписаться от уведомлений\n"
            "/cancel - Отменить текущее действие\n"
            "/help - Эта справка\n\n"
            "🔔 Уведомления:\n"
            "Подпишитесь на уведомления, чтобы получать информацию об изменении статуса ваших заказов прямо в Telegram!\n\n"
            "💡 Совет: Используйте кнопки в меню для удобной навигации!\n\n"
            "❓ Если возникли проблемы, начните заново с команды /start"
        )
        
        await update.message.reply_text(help_message)
    
    async def cancel_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /cancel command"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "cancel_command")
        
        # Clear user session
        session_cleared = self.session_manager.clear_session(user_id)
        
        if session_cleared:
            message = "❌ Текущее действие отменено. Все данные очищены.\n\nИспользуйте /start для начала работы."
        else:
            message = "ℹ️ Нет активных действий для отмены.\n\nИспользуйте /start для начала работы."
        
        await update.message.reply_text(message)
    
    async def handle_callback_query(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard callbacks"""
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        data = query.data
        
        BotErrorHandler.log_user_action(user_id, "callback_query", data)
        
        try:
            if data == "start_order":
                if self.order_handlers:
                    await self.order_handlers.start_order_process(update, context)
                else:
                    await query.message.reply_text("⚠️ Система заказов временно недоступна.")
            elif data == "show_services":
                await self.show_services_catalog(update, context, page=0)
            elif data.startswith("services_page_"):
                page = int(data.split("_")[2])
                await self.show_services_catalog(update, context, page=page)
            elif data.startswith("select_service_"):
                service_id = int(data.split("_")[2])
                await self.handle_service_selection(update, context, service_id)
            elif data.startswith("order_service_"):
                service_id = int(data.split("_")[2])
                if self.order_handlers:
                    await self.order_handlers.handle_service_selection(update, context, service_id)
                else:
                    await query.message.reply_text("⚠️ Система заказов временно недоступна.")
            # Order process callbacks
            elif data.startswith("order_select_service_"):
                service_id = int(data.split("_")[3])
                if self.order_handlers:
                    await self.order_handlers.handle_service_selection(update, context, service_id)
            elif data == "order_cancel":
                if self.order_handlers:
                    await self.order_handlers.cancel_order(update, context)
            elif data == "order_skip_phone":
                if self.order_handlers:
                    await self.order_handlers.skip_phone_step(update, context)
            elif data == "order_continue_with_files":
                if self.order_handlers:
                    await self.order_handlers.continue_with_files(update, context)
            elif data.startswith("order_spec_material_"):
                material = data.split("_")[3]
                if self.order_handlers:
                    await self.order_handlers.handle_material_selection(update, context, material)
            elif data.startswith("order_spec_quality_"):
                quality = data.split("_")[3]
                if self.order_handlers:
                    await self.order_handlers.handle_quality_selection(update, context, quality)
            elif data.startswith("order_spec_infill_"):
                infill = data.split("_")[3]
                if self.order_handlers:
                    await self.order_handlers.handle_infill_selection(update, context, infill)
            elif data == "order_delivery_pickup":
                if self.order_handlers:
                    await self.order_handlers.handle_delivery_pickup(update, context)
            elif data == "order_delivery_shipping":
                if self.order_handlers:
                    await self.order_handlers.handle_delivery_shipping(update, context)
            elif data == "order_confirm":
                if self.order_handlers:
                    await self.order_handlers.confirm_order(update, context)
            elif data == "order_edit_menu":
                if self.order_handlers:
                    await self.order_handlers.show_edit_menu(update, context)
            # Navigation callbacks
            elif data == "order_back_to_services":
                if self.order_handlers:
                    await self.order_handlers.back_to_services(update, context)
            elif data == "order_back_to_contacts":
                if self.order_handlers:
                    await self.order_handlers.back_to_contacts(update, context)
            elif data == "order_back_to_files":
                if self.order_handlers:
                    await self.order_handlers.back_to_files(update, context)
            elif data == "order_back_to_specs":
                if self.order_handlers:
                    await self.order_handlers.back_to_specs(update, context)
            elif data == "order_back_to_delivery":
                if self.order_handlers:
                    await self.order_handlers.back_to_delivery(update, context)
            elif data == "order_back_to_confirmation":
                if self.order_handlers:
                    await self.order_handlers.back_to_confirmation(update, context)
            # Edit callbacks
            elif data == "order_edit_contacts":
                if self.order_handlers:
                    await self.order_handlers.back_to_contacts(update, context)
            elif data == "order_edit_files":
                if self.order_handlers:
                    await self.order_handlers.back_to_files(update, context)
            elif data == "order_edit_specs":
                if self.order_handlers:
                    await self.order_handlers.back_to_specs(update, context)
            elif data == "order_edit_delivery":
                if self.order_handlers:
                    await self.order_handlers.back_to_delivery(update, context)
            elif data == "order_remove_last_file":
                if self.order_handlers:
                    await self.order_handlers.remove_last_file(update, context)
            elif data == "order_back_to_material":
                if self.order_handlers:
                    await self.order_handlers.back_to_material(update, context)
            elif data == "order_back_to_quality":
                if self.order_handlers:
                    await self.order_handlers.back_to_quality(update, context)
            elif data == "main_menu":
                await self.show_main_menu(update, context)
            elif data == "track_order":
                await self.start_order_tracking(update, context)
            elif data == "cancel_tracking":
                context.user_data.pop('tracking_state', None)
                await self.show_main_menu(update, context)
            elif data == "cancel_subscription":
                context.user_data.pop('subscription_state', None)
                await self.show_main_menu(update, context)
            elif data.startswith("order_details_"):
                order_id = int(data.split("_")[2])
                await self.show_order_details(update, context, order_id)
            elif data == "notifications_menu":
                await self.show_notifications_menu(update, context)
            elif data == "subscribe_notifications":
                await self.subscribe_command(update, context)
            elif data == "unsubscribe_notifications":
                await self.unsubscribe_command(update, context)
            elif data == "help":
                await self.help_command(update, context)
            else:
                await query.message.reply_text("❓ Неизвестная команда")
                
        except Exception as e:
            await BotErrorHandler.handle_api_error(update, context, e, "handling callback")
    
    async def handle_text_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        user_id = update.effective_user.id
        text = update.message.text
        
        BotErrorHandler.log_user_action(user_id, "text_message", f"length: {len(text)}")
        
        # Check if user is in tracking mode
        tracking_state = context.user_data.get('tracking_state')
        if tracking_state == 'waiting_for_email':
            await self.handle_tracking_email(update, context, text)
            return
        
        # Check if user is in subscription mode
        subscription_state = context.user_data.get('subscription_state')
        if subscription_state == 'waiting_for_email':
            await self.handle_subscription_email(update, context, text)
            return
        
        # Check if user has active session
        session = self.session_manager.get_session(user_id)
        
        if session and self.order_handlers:
            # Handle message based on current session step
            if session.step == OrderStep.CONTACT_INFO:
                # Determine what contact info we're collecting
                if not session.customer_name:
                    await self.order_handlers.handle_contact_name(update, context, text)
                elif not session.customer_email:
                    await self.order_handlers.handle_contact_email(update, context, text)
                elif session.customer_phone is None:  # None means we haven't asked yet
                    await self.order_handlers.handle_contact_phone(update, context, text)
                else:
                    await update.message.reply_text(
                        "ℹ️ Контактная информация уже собрана. Используйте кнопки для навигации."
                    )
            elif session.step == OrderStep.DELIVERY and session.delivery_needed:
                # Collecting delivery address
                await self.order_handlers.handle_delivery_address(update, context, text)
            else:
                # For other steps, guide user to use buttons
                step_messages = {
                    OrderStep.SERVICE_SELECTION: "Пожалуйста, выберите услугу из предложенного списка.",
                    OrderStep.FILE_UPLOAD: "Отправьте файл модели или используйте кнопки для навигации.",
                    OrderStep.SPECIFICATIONS: "Используйте кнопки для выбора параметров печати.",
                    OrderStep.CONFIRMATION: "Используйте кнопки для подтверждения или редактирования заказа."
                }
                
                message = step_messages.get(session.step, "Используйте кнопки для навигации по заказу.")
                await update.message.reply_text(f"ℹ️ {message}")
        else:
            # No active session
            await update.message.reply_text(
                "👋 Привет! Используйте /start для начала работы или /help для справки."
            )
    
    async def handle_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file uploads"""
        user_id = update.effective_user.id
        file = update.message.document
        
        BotErrorHandler.log_user_action(user_id, "file_upload", file.file_name if file else "no_file")
        
        # Check if user has active order session
        session = self.session_manager.get_session(user_id)
        
        if session and session.step == OrderStep.FILE_UPLOAD and self.order_handlers:
            # Handle file upload in order context
            await self.order_handlers.handle_file_upload(update, context)
        else:
            # Handle file outside of order context
            if not file or not file.file_name:
                await BotErrorHandler.handle_file_error(update, context, "file_not_found")
                return
            
            filename_lower = file.file_name.lower()
            supported_formats = ('.stl', '.obj', '.3mf')
            
            if not filename_lower.endswith(supported_formats):
                await BotErrorHandler.handle_file_error(
                    update, context, "invalid_format", file.file_name
                )
                return
            
            # Check file size (50MB limit)
            if file.file_size and file.file_size > 50 * 1024 * 1024:
                await BotErrorHandler.handle_file_error(
                    update, context, "file_too_large", file.file_name
                )
                return
            
            # File received outside order process
            await update.message.reply_text(
                f"📁 Получил файл модели: {file.file_name}\n"
                f"📏 Размер: {file.file_size / 1024:.1f} KB\n\n"
                "💡 Для оформления заказа используйте команду /order"
            )
    
    async def show_services_catalog(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0):
        """Show services catalog with pagination"""
        user_id = update.effective_user.id
        services_per_page = 5  # Show 5 services per page
        
        try:
            # Fetch services from API
            if not self.api_client:
                raise APIClientError("API client not initialized")
            
            services = await self.api_client.get_services(active_only=True)
            
            if not services:
                message = (
                    "📋 Каталог услуг\n\n"
                    "❌ В данный момент услуги недоступны.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
                await self._send_or_edit_message(update, message)
                return
            
            # Calculate pagination
            total_services = len(services)
            total_pages = (total_services + services_per_page - 1) // services_per_page
            start_idx = page * services_per_page
            end_idx = min(start_idx + services_per_page, total_services)
            page_services = services[start_idx:end_idx]
            
            # Build message
            message_lines = [
                "📋 Каталог услуг NordLayer",
                "",
                "Выберите интересующую вас услугу для получения подробной информации:",
                ""
            ]
            
            # Add services to message
            for i, service in enumerate(page_services, start=start_idx + 1):
                service_name = service.get('name', 'Без названия')
                service_description = service.get('description', '')
                
                # Truncate description for preview
                if service_description and len(service_description) > 80:
                    service_description = service_description[:77] + "..."
                
                message_lines.append(f"{i}. **{service_name}**")
                if service_description:
                    message_lines.append(f"   {service_description}")
                message_lines.append("")
            
            # Add pagination info
            if total_pages > 1:
                message_lines.append(f"📄 Страница {page + 1} из {total_pages}")
            
            message = "\n".join(message_lines)
            
            # Build inline keyboard
            keyboard = []
            
            # Add service selection buttons
            for service in page_services:
                service_id = service.get('id')
                service_name = service.get('name', 'Услуга')
                if service_id:
                    # Truncate button text if too long
                    button_text = service_name if len(service_name) <= 30 else service_name[:27] + "..."
                    keyboard.append([InlineKeyboardButton(
                        f"🛍️ {button_text}", 
                        callback_data=f"select_service_{service_id}"
                    )])
            
            # Add pagination buttons
            pagination_row = []
            if page > 0:
                pagination_row.append(InlineKeyboardButton(
                    "⬅️ Назад", 
                    callback_data=f"services_page_{page - 1}"
                ))
            if page < total_pages - 1:
                pagination_row.append(InlineKeyboardButton(
                    "Вперёд ➡️", 
                    callback_data=f"services_page_{page + 1}"
                ))
            
            if pagination_row:
                keyboard.append(pagination_row)
            
            # Add back to main menu button
            keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_or_edit_message(update, message, reply_markup)
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "fetching services")
        except Exception as e:
            logger.error(f"Unexpected error showing services catalog: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "showing services catalog")
    
    async def handle_service_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int):
        """Handle service selection from catalog"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "service_selection", f"service_id: {service_id}")
        
        try:
            # Fetch services to find the selected one
            if not self.api_client:
                raise APIClientError("API client not initialized")
            
            services = await self.api_client.get_services(active_only=True)
            selected_service = next((s for s in services if s.get('id') == service_id), None)
            
            if not selected_service:
                await update.callback_query.message.reply_text(
                    "❌ Услуга не найдена или недоступна.\n"
                    "Попробуйте выбрать другую услуг из каталога."
                )
                return
            
            # Format service details
            service_name = selected_service.get('name', 'Без названия')
            service_description = selected_service.get('description', 'Описание отсутствует')
            service_category = selected_service.get('category', 'Общие')
            service_features = selected_service.get('features', [])
            
            message_lines = [
                f"🛍️ **{service_name}**",
                "",
                f"📝 **Описание:**",
                service_description,
                "",
                f"📂 **Категория:** {service_category}",
            ]
            
            # Add features if available
            if service_features:
                message_lines.extend([
                    "",
                    "✨ **Особенности:**"
                ])
                for feature in service_features:
                    message_lines.append(f"• {feature}")
            
            message_lines.extend([
                "",
                "💡 Хотите заказать эту услугу? Нажмите кнопку ниже для оформления заказа."
            ])
            
            message = "\n".join(message_lines)
            
            # Build keyboard
            keyboard = [
                [InlineKeyboardButton("🛒 Заказать эту услугу", callback_data=f"order_service_{service_id}")],
                [InlineKeyboardButton("⬅️ Назад к каталогу", callback_data="show_services")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_or_edit_message(update, message, reply_markup)
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "fetching service details")
        except Exception as e:
            logger.error(f"Unexpected error handling service selection: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "handling service selection")
    
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
    
    async def show_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show main menu"""
        user_name = update.effective_user.first_name or "пользователь"
        
        # Create inline keyboard
        keyboard = [
            [InlineKeyboardButton("🛍️ Оформить заказ", callback_data="start_order")],
            [InlineKeyboardButton("📋 Наши услуги", callback_data="show_services")],
            [InlineKeyboardButton("📦 Отследить заказ", callback_data="track_order")],
            [InlineKeyboardButton("🔔 Уведомления", callback_data="notifications_menu")],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data="help")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            f"Добро пожаловать в NordLayer, {user_name}! 🖨️\n\n"
            "Мастерская цифрового ремесла из Карелии.\n"
            "Слой за слоем рождается форма.\n\n"
            "Здесь вы можете:\n"
            "• Оформить заказ на 3D печать\n"
            "• Посмотреть наши услуги\n"
            "• Отследить статус заказа\n\n"
            "Выберите действие:"
        )
        
        await self._send_or_edit_message(update, welcome_text, reply_markup)

    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe command"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "subscribe_command")
        
        # Check if notification service is available
        if not self.notification_service:
            await update.message.reply_text(
                "⚠️ Служба уведомлений временно недоступна."
            )
            return
        
        # Check if user is already subscribed
        subscription = self.notification_service.subscription_manager.get_subscription(user_id)
        if subscription and subscription.is_active:
            message = (
                f"✅ Вы уже подписаны на уведомления!\n\n"
                f"📧 Email: {subscription.email}\n"
                f"🔔 Типы уведомлений: {', '.join(subscription.notification_types)}\n\n"
                f"Для отписки используйте команду /unsubscribe"
            )
            await update.message.reply_text(message)
            return
        
        # Start subscription process
        context.user_data['subscription_state'] = 'waiting_for_email'
        
        message = (
            "🔔 **Подписка на уведомления**\n\n"
            "Чтобы получать уведомления об изменении статуса ваших заказов, "
            "введите email адрес, который вы используете при оформлении заказов:\n\n"
            "💡 Например: example@email.com"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_subscription")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe command"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "unsubscribe_command")
        
        # Check if notification service is available
        if not self.notification_service:
            await update.message.reply_text(
                "⚠️ Служба уведомлений временно недоступна."
            )
            return
        
        # Check if user is subscribed
        subscription = self.notification_service.subscription_manager.get_subscription(user_id)
        if not subscription or not subscription.is_active:
            message = (
                "ℹ️ Вы не подписаны на уведомления.\n\n"
                "Для подписки используйте команду /subscribe"
            )
            await update.message.reply_text(message)
            return
        
        # Unsubscribe user
        success = self.notification_service.subscription_manager.unsubscribe_user(user_id)
        
        if success:
            message = (
                "✅ Вы успешно отписались от уведомлений.\n\n"
                "Вы больше не будете получать уведомления об изменении статуса заказов.\n\n"
                "💡 Для повторной подписки используйте команду /subscribe"
            )
        else:
            message = (
                "❌ Произошла ошибка при отписке.\n"
                "Попробуйте позже или обратитесь к администратору."
            )
        
        await update.message.reply_text(message)

    async def handle_subscription_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
        """Handle email input for subscription"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "subscription_email_input", email)
        
        # Validate email format
        if not self._validate_email(email):
            await update.message.reply_text(
                "❌ Некорректный email адрес.\n"
                "Пожалуйста, введите правильный email в формате: example@email.com"
            )
            return
        
        # Subscribe user
        if self.notification_service:
            success = self.notification_service.subscription_manager.subscribe_user(
                user_id=user_id,
                email=email,
                notification_types={"status_change", "order_ready"}
            )
            
            if success:
                message = (
                    "🎉 **Подписка активирована!**\n\n"
                    f"📧 Email: {email}\n"
                    f"🔔 Вы будете получать уведомления о:\n"
                    "• Изменении статуса заказов\n"
                    "• Готовности заказов к получению\n\n"
                    "💡 Для отписки используйте команду /unsubscribe"
                )
            else:
                message = (
                    "❌ Произошла ошибка при подписке.\n"
                    "Попробуйте позже или обратитесь к администратору."
                )
        else:
            message = (
                "⚠️ Служба уведомлений временно недоступна.\n"
                "Попробуйте позже."
            )
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
        # Clear subscription state
        context.user_data.pop('subscription_state', None)

    async def start_order_tracking(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start order tracking process by requesting email"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "start_order_tracking")
        
        # Store tracking state in context
        context.user_data['tracking_state'] = 'waiting_for_email'
        
        message = (
            "📦 **Отслеживание заказов**\n\n"
            "Для поиска ваших заказов введите email адрес, "
            "который вы указывали при оформлении заказа:\n\n"
            "💡 Например: example@email.com"
        )
        
        keyboard = [
            [InlineKeyboardButton("❌ Отменить", callback_data="cancel_tracking")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_or_edit_message(update, message, reply_markup)

    async def handle_tracking_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
        """Handle email input for order tracking"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "tracking_email_input", email)
        
        # Validate email format
        if not self._validate_email(email):
            await update.message.reply_text(
                "❌ Некорректный email адрес.\n"
                "Пожалуйста, введите правильный email в формате: example@email.com"
            )
            return
        
        try:
            # Show loading message
            loading_message = await update.message.reply_text(
                "🔍 Ищем ваши заказы...\nПожалуйста, подождите."
            )
            
            # Search orders by email
            if not self.api_client:
                raise APIClientError("API client not initialized")
            
            orders = await self.api_client.get_orders_by_email(email)
            
            # Delete loading message
            try:
                await loading_message.delete()
            except Exception:
                pass
            
            if not orders:
                message = (
                    f"📭 **Заказы не найдены**\n\n"
                    f"По email адресу **{email}** заказы не найдены.\n\n"
                    "Возможные причины:\n"
                    "• Заказы оформлены на другой email\n"
                    "• Заказы еще не созданы\n"
                    "• Опечатка в email адресе\n\n"
                    "💡 Попробуйте ввести другой email или создайте новый заказ"
                )
                
                keyboard = [
                    [InlineKeyboardButton("🔄 Попробовать снова", callback_data="track_order")],
                    [InlineKeyboardButton("🛍️ Создать заказ", callback_data="start_order")],
                    [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
                
            else:
                # Show orders list
                await self.show_orders_list(update, context, orders, email)
            
            # Clear tracking state
            context.user_data.pop('tracking_state', None)
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "searching orders")
            context.user_data.pop('tracking_state', None)
        except Exception as e:
            logger.error(f"Unexpected error during order tracking: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "tracking orders")
            context.user_data.pop('tracking_state', None)

    async def show_orders_list(self, update: Update, context: ContextTypes.DEFAULT_TYPE, orders: List[Dict[str, Any]], email: str):
        """Show list of orders for the customer"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "show_orders_list", f"orders_count: {len(orders)}")
        
        # Sort orders by creation date (newest first)
        sorted_orders = sorted(orders, key=lambda x: x.get('created_at', ''), reverse=True)
        
        message_lines = [
            f"📦 **Ваши заказы ({len(orders)})**",
            f"📧 Email: {email}",
            ""
        ]
        
        # Build keyboard with order buttons
        keyboard = []
        
        for i, order in enumerate(sorted_orders[:10]):  # Show max 10 orders
            order_id = order.get('id', 'N/A')
            status = order.get('status', 'unknown')
            service_name = order.get('service_name', 'Услуга')
            created_at = order.get('created_at', '')
            
            # Format creation date
            date_str = "Дата неизвестна"
            if created_at:
                try:
                    from datetime import datetime
                    if 'T' in created_at:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        date_str = dt.strftime('%d.%m.%Y')
                    else:
                        date_str = created_at[:10]  # Take first 10 chars (YYYY-MM-DD)
                except Exception:
                    date_str = str(created_at)[:10] if created_at else "Дата неизвестна"
            
            # Status emoji
            status_emoji = {
                'new': '🆕',
                'confirmed': '✅',
                'in_progress': '🔄',
                'ready': '🎉',
                'completed': '✅',
                'cancelled': '❌'
            }.get(status, '📋')
            
            # Status text in Russian
            status_text = {
                'new': 'Новый',
                'confirmed': 'Подтвержден',
                'in_progress': 'В работе',
                'ready': 'Готов',
                'completed': 'Завершен',
                'cancelled': 'Отменен'
            }.get(status, status.title())
            
            # Add order info to message
            message_lines.append(f"{i+1}. **Заказ #{order_id}** {status_emoji}")
            message_lines.append(f"   📅 {date_str} | 🛍️ {service_name}")
            message_lines.append(f"   📊 Статус: {status_text}")
            message_lines.append("")
            
            # Add button for detailed view
            button_text = f"#{order_id} - {status_text}"
            if len(button_text) > 30:
                button_text = f"#{order_id} - {status_text[:20]}..."
            
            keyboard.append([InlineKeyboardButton(
                f"{status_emoji} {button_text}",
                callback_data=f"order_details_{order_id}"
            )])
        
        if len(orders) > 10:
            message_lines.append(f"... и еще {len(orders) - 10} заказов")
            message_lines.append("Показаны только последние 10 заказов")
            message_lines.append("")
        
        message_lines.extend([
            "💡 Нажмите на заказ для просмотра подробной информации",
            "",
            "🔔 Вы будете получать уведомления об изменении статуса заказов"
        ])
        
        # Add navigation buttons
        keyboard.extend([
            [InlineKeyboardButton("🔄 Обновить список", callback_data="track_order")],
            [InlineKeyboardButton("🛍️ Создать новый заказ", callback_data="start_order")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ])
        
        message = "\n".join(message_lines)
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')

    async def show_order_details(self, update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int):
        """Show detailed information about a specific order"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "show_order_details", f"order_id: {order_id}")
        
        try:
            # For now, we'll need to search by email again to find the specific order
            # In a real implementation, we might want to store the orders in context
            # or have a direct API endpoint to get order by ID
            
            # This is a simplified approach - in production, you might want to implement
            # a more efficient method or store order data temporarily
            
            message = (
                f"📋 **Заказ #{order_id}**\n\n"
                "🔍 Загружаем подробную информацию...\n"
                "Эта функция будет полностью реализована в следующих итерациях.\n\n"
                "Для получения актуальной информации о заказе "
                "обратитесь к администратору или проверьте email."
            )
            
            keyboard = [
                [InlineKeyboardButton("⬅️ Назад к списку", callback_data="track_order")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await self._send_or_edit_message(update, message, reply_markup)
            
        except Exception as e:
            logger.error(f"Error showing order details for order {order_id}: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "showing order details")

    async def show_notifications_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show notifications management menu"""
        user_id = update.effective_user.id
        BotErrorHandler.log_user_action(user_id, "show_notifications_menu")
        
        # Check if notification service is available
        if not self.notification_service:
            message = (
                "⚠️ Служба уведомлений временно недоступна.\n"
                "Попробуйте позже."
            )
            keyboard = [
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await self._send_or_edit_message(update, message, reply_markup)
            return
        
        # Check subscription status
        subscription = self.notification_service.subscription_manager.get_subscription(user_id)
        
        if subscription and subscription.is_active:
            # User is subscribed
            message = (
                "🔔 **Управление уведомлениями**\n\n"
                "✅ Вы подписаны на уведомления\n\n"
                f"📧 Email: {subscription.email}\n"
                f"🔔 Типы уведомлений:\n"
                f"• Изменение статуса заказов\n"
                f"• Готовность заказов к получению\n\n"
                f"📅 Подписка с: {subscription.subscribed_at.strftime('%d.%m.%Y')}"
            )
            
            keyboard = [
                [InlineKeyboardButton("❌ Отписаться", callback_data="unsubscribe_notifications")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        else:
            # User is not subscribed
            message = (
                "🔔 **Управление уведомлениями**\n\n"
                "❌ Вы не подписаны на уведомления\n\n"
                "Подпишитесь, чтобы получать уведомления о:\n"
                "• Изменении статуса ваших заказов\n"
                "• Готовности заказов к получению\n\n"
                "💡 Уведомления приходят прямо в этот чат!"
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Подписаться", callback_data="subscribe_notifications")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)

    def _validate_email(self, email: str) -> bool:
        """Validate email address format"""
        import re
        if not email:
            return False
        # Basic email validation pattern
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email.strip()))

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE):
        """Global error handler"""
        logger.error(f"Exception while handling an update: {context.error}")
        
        # Try to send error message to user if possible
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "⚠️ Произошла неожиданная ошибка. Попробуйте позже или используйте /start"
                )
            except Exception:
                pass  # Ignore errors when sending error messages
    
    async def cleanup_sessions_periodically(self):
        """Periodically clean up old sessions"""
        while not self._shutdown_event.is_set():
            try:
                self.session_manager.cleanup_old_sessions(settings.session_cleanup_hours)
                await asyncio.sleep(3600)  # Run every hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")
                await asyncio.sleep(3600)
    
    async def run(self):
        """Start the bot with proper initialization and cleanup"""
        try:
            await self.initialize()
            
            if not self.application:
                raise RuntimeError("Application not initialized")
            
            # Start health check server
            self.health_runner = await self.health_server.start()
            
            # Start webhook server if configured
            if self.webhook_handler:
                webhook_port = getattr(settings, 'webhook_port', 8081)
                self.webhook_runner = await self.webhook_handler.start_server(port=webhook_port)
                logger.info(f"Webhook server started on port {webhook_port}")
            
            # Start session cleanup task
            cleanup_task = asyncio.create_task(self.cleanup_sessions_periodically())
            
            logger.info("Starting Telegram bot...")
            BotErrorHandler.log_system_event("bot_started", f"API URL: {settings.api_base_url}")
            
            # Start polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down bot...")
        BotErrorHandler.log_system_event("bot_shutdown")
        
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
            
            if self.health_runner:
                await self.health_server.stop(self.health_runner)
            
            if self.webhook_runner and self.webhook_handler:
                await self.webhook_handler.stop_server(self.webhook_runner)
            
            if self.api_client:
                await self.api_client.close()
            
            logger.info("Bot shutdown complete")
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self._shutdown_event.set()


async def main():
    """Main entry point"""
    bot = TelegramBot()
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        bot.signal_handler(signum, frame)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.run()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())