import logging
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from queue import Queue
import threading

from config import Settings
from parser import EmailParser

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(self, settings: Settings, email_queue: Queue):
        self.settings = settings
        self.email_queue = email_queue
        self.parser = EmailParser(
            max_preview_length=settings.max_preview_length,
            spam_keywords=settings.spam_keywords
        )
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self.running = False
        self.process_thread: Optional[threading.Thread] = None
        self.active_groups = set()  # Простой список активных групп
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        await update.message.reply_text(
            "👋 Email Notifier Bot\n\n"
            "Команды:\n"
            "/subscribe - Подписаться на уведомления\n"
            "/unsubscribe - Отписаться\n"
            "/status - Статус"
        )
    
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe command"""
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("Работает только в группах!")
            return
        
        chat_id = update.effective_chat.id
        self.active_groups.add(chat_id)
        
        await update.message.reply_text(
            f"✅ Группа подписана!\n"
            f"Будете получать уведомления о новых письмах."
        )
        logger.info(f"Group {chat_id} subscribed")
    
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe command"""
        chat_id = update.effective_chat.id
        
        if chat_id in self.active_groups:
            self.active_groups.remove(chat_id)
            await update.message.reply_text("✅ Группа отписана")
        else:
            await update.message.reply_text("Группа не была подписана")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        chat_id = update.effective_chat.id
        status = "подписана ✅" if chat_id in self.active_groups else "не подписана ❌"
        
        await update.message.reply_text(
            f"📊 Статус\n\n"
            f"Группа: {status}\n"
            f"Email аккаунтов: {len(self.settings.email_accounts)}\n"
            f"Активных групп: {len(self.active_groups)}"
        )
    
    async def handle_read_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the Read button - ПРОСТО УДАЛЯЕМ!"""
        query = update.callback_query
        
        # Подтверждаем получение callback
        await query.answer("Обработка...")
        
        # Пытаемся удалить сообщение
        try:
            await query.message.delete()
            logger.info(f"Message deleted by {query.from_user.id}")
        except Exception as e:
            logger.error(f"Failed to delete: {e}")
            # Если не можем удалить - хотя бы редактируем
            try:
                await query.message.edit_text(
                    "✅ Прочитано",
                    reply_markup=None
                )
            except:
                pass
    
    async def send_email_notification(self, email_data: dict) -> bool:
        """Send email notification to all subscribed groups"""
        if not self.active_groups:
            logger.warning("No subscribed groups")
            return False
        
        # Format message
        message = self.parser.format_telegram_message(
            account_label=email_data['account_label'],
            account_email=email_data['account_email'],
            sender=email_data['sender'],
            subject=email_data['subject'],
            body_preview=email_data['body_preview']
        )
        
        # Simple Read button
        keyboard = [[InlineKeyboardButton("Read ✅", callback_data="read")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send to all groups
        for chat_id in list(self.active_groups):
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
                logger.info(f"Sent to group {chat_id}")
            except Exception as e:
                logger.error(f"Failed to send to {chat_id}: {e}")
                # Remove inactive group
                if "chat not found" in str(e).lower():
                    self.active_groups.discard(chat_id)
        
        return True
    
    def process_email_queue(self):
        """Process emails from queue"""
        logger.info("Email processor started")
        
        processed_emails = set()  # Простой трекинг обработанных писем
        
        while self.running:
            try:
                # Get email with timeout
                email_data = self.email_queue.get(timeout=1)
                
                # Parse email
                parsed = self.parser.parse_email(email_data['raw_email'])
                if not parsed:
                    continue
                
                # Skip spam
                if parsed['is_spam']:
                    logger.info(f"Skipping spam: {parsed['subject']}")
                    continue
                
                # Simple duplicate check
                email_key = f"{parsed['message_id']}_{parsed['subject']}"
                if email_key in processed_emails:
                    continue
                
                processed_emails.add(email_key)
                
                # Keep only last 100 emails in memory
                if len(processed_emails) > 100:
                    processed_emails.clear()
                
                # Prepare notification
                notification = {
                    'account_label': email_data['account_label'],
                    'account_email': email_data['account_email'],
                    'sender': parsed['sender'],
                    'subject': parsed['subject'],
                    'body_preview': parsed['body_preview']
                }
                
                # Send notification
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self.send_email_notification(notification))
                loop.close()
                
            except Exception as e:
                if self.running and "Empty" not in str(e):
                    logger.error(f"Queue error: {e}")
        
        logger.info("Email processor stopped")
    
    async def initialize(self):
        """Initialize bot"""
        self.application = Application.builder().token(self.settings.telegram_bot_token).build()
        self.bot = self.application.bot
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # ВАЖНО: Обработчик для ЛЮБОГО callback с кнопки
        self.application.add_handler(CallbackQueryHandler(self.handle_read_button))
        
        await self.application.initialize()
        await self.application.start()
        
        logger.info("Bot initialized")
    
    async def start(self):
        """Start bot"""
        self.running = True
        
        # Start email processor
        self.process_thread = threading.Thread(target=self.process_email_queue)
        self.process_thread.daemon = True
        self.process_thread.start()
        
        # Start polling
        await self.application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        logger.info("Bot started")
    
    async def stop(self):
        """Stop bot"""
        self.running = False
        
        if self.process_thread:
            self.process_thread.join(timeout=5)
        
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("Bot stopped")
    
    async def run(self):
        """Run bot"""
        await self.initialize()
        await self.start()
        
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()