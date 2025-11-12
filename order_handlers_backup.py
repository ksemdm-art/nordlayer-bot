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
    
    async def handle_contact_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE, name: str):
        """Handle customer name input"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.CONTACT_INFO:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Validate name
        if not self._validate_name(name):
            await BotErrorHandler.handle_validation_error(update, context, "name")
            return
        
        # Save name and ask for email
        session.customer_name = name.strip()
        
        message = (
            f"✅ Имя: **{session.customer_name}**\n\n"
            "Теперь введите ваш **email адрес**:"
        )
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Изменить имя", callback_data="order_edit_name")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_contact_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE, email: str):
        """Handle customer email input"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.CONTACT_INFO:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Validate email
        if not self._validate_email(email):
            await BotErrorHandler.handle_validation_error(update, context, "email")
            return
        
        # Save email and ask for phone
        session.customer_email = email.strip().lower()
        
        message = (
            f"✅ Email: **{session.customer_email}**\n\n"
            "Введите ваш **номер телефона** (необязательно):\n"
            "Формат: +7 900 123-45-67 или пропустите этот шаг"
        )
        
        keyboard = [
            [InlineKeyboardButton("⏭️ Пропустить телефон", callback_data="order_skip_phone")],
            [InlineKeyboardButton("⬅️ Изменить email", callback_data="order_edit_email")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def handle_contact_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE, phone: str):
        """Handle customer phone input"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.CONTACT_INFO:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Validate phone if provided
        if phone and not self._validate_phone(phone):
            await BotErrorHandler.handle_validation_error(update, context, "phone")
            return
        
        # Save phone and move to file upload
        session.customer_phone = phone.strip() if phone else None
        session.step = OrderStep.FILE_UPLOAD
        
        await self.show_file_upload_step(update, context)
    
    async def skip_phone_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Skip phone input and move to file upload"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.CONTACT_INFO:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        session.customer_phone = None
        session.step = OrderStep.FILE_UPLOAD
        
        await self.show_file_upload_step(update, context)
    
    async def show_file_upload_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show file upload step"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session:
            await BotErrorHandler.handle_session_error(update, context, "session_not_found")
            return
        
        # Show contact summary
        contact_summary = [
            "📋 Контактная информация:",
            f"👤 Имя: {session.customer_name}",
            f"📧 Email: {session.customer_email}"
        ]
        
        if session.customer_phone:
            contact_summary.append(f"📱 Телефон: {session.customer_phone}")
        
        uploaded_files_info = ""
        if session.files:
            uploaded_files_info = f"\n\n📁 Загружено файлов: {len(session.files)}"
            for i, file_info in enumerate(session.files, 1):
                uploaded_files_info += f"\n{i}. {file_info.get('filename', 'Файл')}"
        
        message = (
            "\n".join(contact_summary) + 
            "\n\n📁 Загрузка файлов модели\n\n"
            "Отправьте файлы ваших 3D моделей.\n"
            "Поддерживаемые форматы: **.stl**, **.obj**, **.3mf**\n"
            "Максимальный размер файла: **50MB**" +
            uploaded_files_info +
            "\n\nВы можете загрузить несколько файлов."
        )
        
        # Build keyboard
        keyboard = []
        
        if session.files:
            keyboard.append([InlineKeyboardButton("✅ Продолжить с загруженными файлами", callback_data="order_continue_with_files")])
        
        keyboard.extend([
            [InlineKeyboardButton("⬅️ Изменить контакты", callback_data="order_back_to_contacts")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_file_upload(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle file upload from user"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.FILE_UPLOAD:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        file = update.message.document
        if not file:
            await update.message.reply_text("❌ Файл не найден. Попробуйте отправить файл заново.")
            return
        
        # Validate file
        if not file.file_name:
            await BotErrorHandler.handle_file_error(update, context, "file_not_found")
            return
        
        filename_lower = file.file_name.lower()
        supported_formats = ('.stl', '.obj', '.3mf')
        
        if not filename_lower.endswith(supported_formats):
            await BotErrorHandler.handle_file_error(update, context, "invalid_format", file.file_name)
            return
        
        # Check file size (50MB limit)
        if file.file_size and file.file_size > 50 * 1024 * 1024:
            await BotErrorHandler.handle_file_error(update, context, "file_too_large", file.file_name)
            return
        
        try:
            # Download file from Telegram
            file_obj = await context.bot.get_file(file.file_id)
            file_data = await file_obj.download_as_bytearray()
            
            # Upload to API
            upload_result = await self.api_client.upload_file(
                file_data=bytes(file_data),
                filename=file.file_name,
                content_type=file.mime_type
            )
            
            # Save file info to session
            file_info = {
                "filename": file.file_name,
                "size": file.file_size,
                "telegram_file_id": file.file_id,
                "upload_result": upload_result
            }
            session.files.append(file_info)
            
            # Confirm upload
            message = (
                f"✅ Файл **{file.file_name}** успешно загружен!\n"
                f"📏 Размер: {file.file_size / 1024:.1f} KB\n\n"
                f"📁 Всего файлов: {len(session.files)}\n\n"
                "Вы можете загрузить еще файлы или продолжить оформление заказа."
            )
            
            keyboard = [
                [InlineKeyboardButton("✅ Продолжить оформление", callback_data="order_continue_with_files")],
                [InlineKeyboardButton("🗑️ Удалить последний файл", callback_data="order_remove_last_file")],
                [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(message, reply_markup=reply_markup, parse_mode='Markdown')
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "uploading file")
        except Exception as e:
            logger.error(f"Unexpected error uploading file: {e}")
            await BotErrorHandler.handle_file_error(update, context, "upload_failed", file.file_name)
    
    async def continue_with_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Continue to specifications step after file upload"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or not session.files:
            await update.callback_query.message.reply_text(
                "❌ Необходимо загрузить хотя бы один файл для продолжения."
            )
            return
        
        session.step = OrderStep.SPECIFICATIONS
        await self.show_specifications_step(update, context)
    
    async def show_specifications_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show printing specifications selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session:
            await BotErrorHandler.handle_session_error(update, context, "session_not_found")
            return
        
        message = (
            "⚙️ Параметры печати\n\n"
            "Выберите материал для печати:"
        )
        
        # Material selection keyboard
        keyboard = [
            [InlineKeyboardButton("🔴 PLA (базовый)", callback_data="order_spec_material_pla")],
            [InlineKeyboardButton("🟡 PETG (прочный)", callback_data="order_spec_material_petg")],
            [InlineKeyboardButton("⚫ ABS (термостойкий)", callback_data="order_spec_material_abs")],
            [InlineKeyboardButton("🔵 TPU (гибкий)", callback_data="order_spec_material_tpu")],
            [InlineKeyboardButton("⬅️ Назад к файлам", callback_data="order_back_to_files")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_material_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, material: str):
        """Handle material selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.SPECIFICATIONS:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Save material
        session.specifications["material"] = material
        
        # Show quality selection
        material_names = {
            "pla": "PLA (базовый)",
            "petg": "PETG (прочный)", 
            "abs": "ABS (термостойкий)",
            "tpu": "TPU (гибкий)"
        }
        
        message = (
            f"✅ Материал: **{material_names.get(material, material)}**\n\n"
            "Выберите качество печати:"
        )
        
        keyboard = [
            [InlineKeyboardButton("🟢 Черновое (0.3мм, быстро)", callback_data="order_spec_quality_draft")],
            [InlineKeyboardButton("🟡 Стандартное (0.2мм)", callback_data="order_spec_quality_standard")],
            [InlineKeyboardButton("🔴 Высокое (0.1мм, медленно)", callback_data="order_spec_quality_high")],
            [InlineKeyboardButton("⬅️ Изменить материал", callback_data="order_back_to_material")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_quality_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, quality: str):
        """Handle quality selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.SPECIFICATIONS:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Save quality
        session.specifications["quality"] = quality
        
        # Show infill selection
        quality_names = {
            "draft": "Черновое (0.3мм)",
            "standard": "Стандартное (0.2мм)",
            "high": "Высокое (0.1мм)"
        }
        
        message = (
            f"✅ Качество: **{quality_names.get(quality, quality)}**\n\n"
            "Выберите заполнение модели:"
        )
        
        keyboard = [
            [InlineKeyboardButton("📦 15% (легкая модель)", callback_data="order_spec_infill_15")],
            [InlineKeyboardButton("📦 30% (стандарт)", callback_data="order_spec_infill_30")],
            [InlineKeyboardButton("📦 50% (прочная)", callback_data="order_spec_infill_50")],
            [InlineKeyboardButton("📦 100% (максимальная прочность)", callback_data="order_spec_infill_100")],
            [InlineKeyboardButton("⬅️ Изменить качество", callback_data="order_back_to_quality")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_infill_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, infill: str):
        """Handle infill selection and move to delivery"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.SPECIFICATIONS:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Save infill
        session.specifications["infill"] = infill
        session.step = OrderStep.DELIVERY
        
        await self.show_delivery_step(update, context)
    
    async def show_delivery_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show delivery options"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session:
            await BotErrorHandler.handle_session_error(update, context, "session_not_found")
            return
        
        # Show specifications summary
        specs_summary = []
        if session.specifications.get("material"):
            material_names = {"pla": "PLA", "petg": "PETG", "abs": "ABS", "tpu": "TPU"}
            specs_summary.append(f"🔹 Материал: {material_names.get(session.specifications['material'], session.specifications['material'])}")
        
        if session.specifications.get("quality"):
            quality_names = {"draft": "Черновое", "standard": "Стандартное", "high": "Высокое"}
            specs_summary.append(f"🔹 Качество: {quality_names.get(session.specifications['quality'], session.specifications['quality'])}")
        
        if session.specifications.get("infill"):
            specs_summary.append(f"🔹 Заполнение: {session.specifications['infill']}%")
        
        message = (
            "🚚 Способ получения заказа\n\n"
            "Параметры печати:\n" + "\n".join(specs_summary) + "\n\n"
            "Как вы хотите получить готовый заказ?"
        )
        
        keyboard = [
            [InlineKeyboardButton("🏪 Самовывоз (бесплатно)", callback_data="order_delivery_pickup")],
            [InlineKeyboardButton("🚚 Доставка", callback_data="order_delivery_shipping")],
            [InlineKeyboardButton("⬅️ Изменить параметры", callback_data="order_back_to_specs")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_delivery_pickup(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle pickup selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.DELIVERY:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        session.delivery_needed = False
        session.delivery_details = None
        session.step = OrderStep.CONFIRMATION
        
        await self.show_confirmation_step(update, context)
    
    async def handle_delivery_shipping(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle shipping selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.DELIVERY:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        session.delivery_needed = True
        
        message = (
            "📍 Адрес доставки\n\n"
            "Введите полный адрес доставки:\n"
            "(город, улица, дом, квартира)"
        )
        
        keyboard = [
            [InlineKeyboardButton("⬅️ Назад к способу получения", callback_data="order_back_to_delivery")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def handle_delivery_address(self, update: Update, context: ContextTypes.DEFAULT_TYPE, address: str):
        """Handle delivery address input"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or session.step != OrderStep.DELIVERY:
            await BotErrorHandler.handle_session_error(update, context, "invalid_step")
            return
        
        # Validate address (basic check)
        if len(address.strip()) < 10:
            await update.message.reply_text(
                "❌ Адрес слишком короткий. Пожалуйста, укажите полный адрес доставки."
            )
            return
        
        session.delivery_details = address.strip()
        session.step = OrderStep.CONFIRMATION
        
        await self.show_confirmation_step(update, context)
    
    async def show_confirmation_step(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show order confirmation with full summary"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session:
            await BotErrorHandler.handle_session_error(update, context, "session_not_found")
            return
        
        # Get full order summary
        summary = session.get_summary()
        
        message = (
            "✅ Подтверждение заказа\n\n" +
            summary + "\n\n" +
            "Проверьте все данные и подтвердите заказ.\n"
            "После подтверждения заказ будет отправлен в обработку."
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить заказ", callback_data="order_confirm")],
            [InlineKeyboardButton("✏️ Редактировать", callback_data="order_edit_menu")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def show_edit_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show edit menu for order modification"""
        message = (
            "✏️ Что вы хотите изменить?\n\n"
            "Выберите раздел для редактирования:"
        )
        
        keyboard = [
            [InlineKeyboardButton("👤 Контактные данные", callback_data="order_edit_contacts")],
            [InlineKeyboardButton("📁 Файлы", callback_data="order_edit_files")],
            [InlineKeyboardButton("⚙️ Параметры печати", callback_data="order_edit_specs")],
            [InlineKeyboardButton("🚚 Доставка", callback_data="order_edit_delivery")],
            [InlineKeyboardButton("⬅️ Назад к подтверждению", callback_data="order_back_to_confirmation")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
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
            
        except APIClientError as e:
            await BotErrorHandler.handle_api_error(update, context, e, "creating order")
        except Exception as e:
            logger.error(f"Unexpected error creating order: {e}")
            await BotErrorHandler.handle_api_error(update, context, e, "creating order")
    
    async def cancel_order(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Cancel current order process"""
        user_id = update.effective_user.id
        
        # Clear session
        session_cleared = self.session_manager.clear_session(user_id)
        
        message = (
            "❌ Заказ отменен\n\n"
            "Все данные очищены. Вы можете начать новый заказ в любое время.\n\n"
            "Используйте /start для возврата в главное меню."
        )
        
        keyboard = [
            [InlineKeyboardButton("🆕 Создать новый заказ", callback_data="start_order")],
            [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await self._send_or_edit_message(update, message, reply_markup)
        
        BotErrorHandler.log_user_action(user_id, "order_cancelled")
    
    # Navigation handlers
    async def back_to_services(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to service selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.SERVICE_SELECTION
        await self.show_service_selection(update, context)
    
    async def back_to_contacts(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to contact info"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.CONTACT_INFO
        await self.show_contact_info_collection(update, context)
    
    async def back_to_files(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to file upload"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.FILE_UPLOAD
        await self.show_file_upload_step(update, context)
    
    async def back_to_specs(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to specifications"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.SPECIFICATIONS
        await self.show_specifications_step(update, context)
    
    async def back_to_delivery(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to delivery options"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.DELIVERY
        await self.show_delivery_step(update, context)
    
    async def back_to_confirmation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to confirmation"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            session.step = OrderStep.CONFIRMATION
        await self.show_confirmation_step(update, context)
    
    async def remove_last_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove the last uploaded file"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        
        if not session or not session.files:
            await update.callback_query.message.reply_text(
                "❌ Нет файлов для удаления."
            )
            return
        
        # Remove last file
        removed_file = session.files.pop()
        
        message = (
            f"🗑️ Файл **{removed_file.get('filename', 'файл')}** удален.\n\n"
            f"📁 Осталось файлов: {len(session.files)}\n\n"
            "Вы можете загрузить новые файлы или продолжить оформление."
        )
        
        keyboard = []
        if session.files:
            keyboard.append([InlineKeyboardButton("✅ Продолжить с оставшимися файлами", callback_data="order_continue_with_files")])
        
        keyboard.extend([
            [InlineKeyboardButton("🗑️ Удалить еще файл", callback_data="order_remove_last_file")] if session.files else [],
            [InlineKeyboardButton("⬅️ Назад к контактам", callback_data="order_back_to_contacts")],
            [InlineKeyboardButton("❌ Отменить заказ", callback_data="order_cancel")]
        ])
        
        # Remove empty lists
        keyboard = [row for row in keyboard if row]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await self._send_or_edit_message(update, message, reply_markup)
    
    async def back_to_material(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to material selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session:
            # Clear quality and infill selections
            session.specifications.pop("quality", None)
            session.specifications.pop("infill", None)
        await self.show_specifications_step(update, context)
    
    async def back_to_quality(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Go back to quality selection"""
        user_id = update.effective_user.id
        session = self.session_manager.get_session(user_id)
        if session and session.specifications.get("material"):
            # Clear infill selection but keep material
            session.specifications.pop("infill", None)
            await self.handle_material_selection(update, context, session.specifications["material"])
        else:
            await self.show_specifications_step(update, context)
    
    # Utility methods
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