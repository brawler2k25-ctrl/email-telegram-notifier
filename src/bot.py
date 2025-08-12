import logging
import asyncio
import json
from typing import Optional, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import TelegramError
from queue import Queue
import threading

from config import Settings
from db import EmailDatabase
from parser import EmailParser

logger = logging.getLogger(__name__)

class TelegramBot:
    def __init__(
        self,
        settings: Settings,
        database: EmailDatabase,
        email_queue: Queue
    ):
        self.settings = settings
        self.database = database
        self.email_queue = email_queue
        self.parser = EmailParser(
            max_preview_length=settings.max_preview_length,
            spam_keywords=settings.spam_keywords
        )
        self.application: Optional[Application] = None
        self.bot: Optional[Bot] = None
        self.running = False
        self.process_thread: Optional[threading.Thread] = None
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        if not update.effective_chat.type in ['group', 'supergroup']:
            await update.message.reply_text("Этот бот работает только в группах!")
            return
        
        group_info = self.database.get_group_by_chat_id(update.effective_chat.id)
        if group_info:
            stats = self.database.get_group_stats(update.effective_chat.id)
            message = (
                f"👋 Добро пожаловать в Email Notifier Bot!\n\n"
                f"📊 Статистика группы:\n"
                f"• Всего уведомлений: {stats.get('total_notifications', 0)}\n"
                f"• Обработано: {stats.get('handled', 0)}\n"
                f"• Ожидает: {stats.get('unhandled', 0)}\n\n"
                f"Используйте команды:\n"
                f"/subscribe - Подписаться на уведомления\n"
                f"/unsubscribe - Отписаться\n"
                f"/filter отдел1,отдел2 - Фильтр по отделам\n"
                f"/status - Статистика"
            )
        else:
            message = (
                "👋 Добро пожаловать в Email Notifier Bot!\n\n"
                "Эта группа не подписана на уведомления.\n"
                "Используйте /subscribe для подписки."
            )
        
        await update.message.reply_text(message)
    
    async def subscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /subscribe command"""
        if not update.effective_chat.type in ['group', 'supergroup']:
            await update.message.reply_text("Этот бот работает только в группах!")
            return
        
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Unknown Group"
        user_id = update.effective_user.id
        
        # Add or update group
        group_id = self.database.add_group(chat_id, chat_title, user_id)
        
        if group_id:
            message = (
                f"✅ Группа '{chat_title}' подписана на уведомления!\n\n"
                f"Теперь вы будете получать уведомления от всех email аккаунтов.\n"
                f"Используйте /filter для настройки фильтров по отделам."
            )
        else:
            message = "❌ Ошибка при подписке группы."
        
        await update.message.reply_text(message)
    
    async def unsubscribe_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /unsubscribe command"""
        if not update.effective_chat.type in ['group', 'supergroup']:
            await update.message.reply_text("Этот бот работает только в группах!")
            return
        
        chat_id = update.effective_chat.id
        
        if self.database.remove_group(chat_id):
            message = "✅ Группа отписана от уведомлений."
        else:
            message = "❌ Группа не была подписана."
        
        await update.message.reply_text(message)
    
    async def filter_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /filter command"""
        if not update.effective_chat.type in ['group', 'supergroup']:
            await update.message.reply_text("Этот бот работает только в группах!")
            return
        
        chat_id = update.effective_chat.id
        
        # Check if group is subscribed
        group_info = self.database.get_group_by_chat_id(chat_id)
        if not group_info:
            await update.message.reply_text("❌ Группа не подписана. Используйте /subscribe")
            return
        
        # Parse filter arguments
        if context.args:
            filter_text = " ".join(context.args)
            if filter_text.lower() == "clear":
                # Clear filter
                self.database.update_group_filter(chat_id, None)
                await update.message.reply_text("✅ Фильтр очищен. Теперь получаете уведомления от всех отделов.")
                return
            
            # Set filter
            filters = [f.strip() for f in filter_text.split(",")]
            self.database.update_group_filter(chat_id, filters)
            
            filter_list = ", ".join(filters)
            message = f"✅ Установлен фильтр: {filter_list}\n\nТеперь получаете уведомления только от этих отделов."
        else:
            # Show current filter
            current_filter = group_info.get('filter_accounts')
            if current_filter:
                filter_accounts = json.loads(current_filter)
                filter_list = ", ".join(filter_accounts)
                message = f"🔍 Текущий фильтр: {filter_list}\n\n"
            else:
                message = "🔍 Фильтр не установлен (получаете от всех отделов)\n\n"
            
            message += (
                "Использование:\n"
                "/filter отдел1,отдел2 - установить фильтр\n"
                "/filter clear - очистить фильтр"
            )
        
        await update.message.reply_text(message)
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        if not update.effective_chat.type in ['group', 'supergroup']:
            await update.message.reply_text("Этот бот работает только в группах!")
            return
        
        chat_id = update.effective_chat.id
        group_info = self.database.get_group_by_chat_id(chat_id)
        
        if not group_info:
            await update.message.reply_text("❌ Группа не подписана. Используйте /subscribe")
            return
        
        stats = self.database.get_group_stats(chat_id)
        overall_stats = self.database.get_overall_stats()
        
        # Get filter info
        current_filter = group_info.get('filter_accounts')
        if current_filter:
            filter_accounts = json.loads(current_filter)
            filter_text = f"🔍 Фильтр: {', '.join(filter_accounts)}"
        else:
            filter_text = "🔍 Фильтр: Все отделы"
        
        message = (
            f"📊 *Статистика группы*\n\n"
            f"📬 Группа: {group_info['chat_title']}\n"
            f"{filter_text}\n\n"
            f"*Уведомления в этой группе:*\n"
            f"• Всего: {stats.get('total_notifications', 0)}\n"
            f"• Обработано: {stats.get('handled', 0)}\n"
            f"• Ожидает: {stats.get('unhandled', 0)}\n\n"
            f"*Общая статистика бота:*\n"
            f"• Email аккаунтов: {len(self.settings.email_accounts)}\n"
            f"• Активных групп: {overall_stats.get('active_groups', 0)}\n"
            f"• Всего писем: {overall_stats.get('total_emails', 0)}"
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = (
            "🤖 *Email Notifier Bot*\n\n"
            "*Команды для групп:*\n"
            "/subscribe - Подписать группу на уведомления\n"
            "/unsubscribe - Отписать группу\n"
            "/filter отдел1,отдел2 - Настроить фильтр по отделам\n"
            "/filter clear - Очистить фильтр\n"
            "/status - Показать статистику\n"
            "/help - Показать эту справку\n\n"
            "*Как использовать:*\n"
            "1. Добавьте бота в группу как администратора\n"
            "2. Отправьте /subscribe для подписки\n"
            "3. Настройте фильтры при необходимости\n"
            "4. Нажимайте 'Read ✅' для обработки писем"
        )
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def handle_read_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the Read button callback"""
        query = update.callback_query
        
        if query.data.startswith("read_"):
            telegram_message_id = query.message.message_id
            user_id = query.from_user.id
            
            # Mark as handled in database
            if self.database.mark_notification_handled(telegram_message_id, user_id):
                # Delete the message for everyone
                try:
                    await query.message.delete()
                    await query.answer("✅ Письмо помечено как прочитанное", show_alert=False)
                    
                    logger.info(f"Email notification handled by user {user_id}")
                except TelegramError as e:
                    logger.error(f"Error deleting message: {e}")
                    await query.answer("❌ Ошибка при удалении сообщения", show_alert=True)
            else:
                await query.answer("⚠️ Письмо уже обработано", show_alert=True)
    
    async def send_email_notification(self, email_data: dict, group_id: int, chat_id: int) -> Optional[int]:
        """Send email notification to specific group"""
        try:
            # Format the message
            message = self.parser.format_telegram_message(
                account_label=email_data['account_label'],
                account_email=email_data['account_email'],
                sender=email_data['sender'],
                subject=email_data['subject'],
                body_preview=email_data['body_preview']
            )
            
            # Create inline keyboard with Read button
            keyboard = [[InlineKeyboardButton("Read ✅", callback_data=f"read_{email_data['email_id']}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send message
            sent_message = await self.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='MarkdownV2',
                reply_markup=reply_markup
            )
            
            # Save notification to database
            self.database.add_notification(email_data['email_id'], group_id, sent_message.message_id)
            
            return sent_message.message_id
            
        except Exception as e:
            logger.error(f"Error sending Telegram notification to group {chat_id}: {e}")
            return None
    
    def should_send_to_group(self, group_info: dict, email_account_label: str) -> bool:
        """Check if email should be sent to specific group based on filters"""
        filter_accounts = group_info.get('filter_accounts')
        if not filter_accounts:
            return True  # No filter, send all
        
        try:
            filters = json.loads(filter_accounts)
            return email_account_label in filters
        except:
            return True  # Error in filter, send all
    
    def process_email_queue(self):
        """Process emails from the queue"""
        logger.info("Starting email queue processor")
        
        while self.running:
            try:
                # Get email from queue (with timeout to check running flag)
                email_data = self.email_queue.get(timeout=1)
                
                # Parse the email
                parsed = self.parser.parse_email(email_data['raw_email'])
                
                if not parsed:
                    logger.warning("Failed to parse email")
                    continue
                
                # Check if it's spam
                if parsed['is_spam']:
                    logger.info(f"Skipping spam/auto-reply email: {parsed['subject']}")
                    continue
                
                # Check if email already exists
                if self.database.email_exists(
                    parsed['message_id'],
                    parsed['sender'],
                    parsed['subject']
                ):
                    logger.info(f"Email already exists: {parsed['subject']}")
                    continue
                
                # Add to database
                email_id = self.database.add_email(
                    message_id=parsed['message_id'],
                    email_account=f"{email_data['account_label']} ({email_data['account_email']})",
                    sender=parsed['sender'],
                    subject=parsed['subject'],
                    body_preview=parsed['body_preview'],
                    received_date=parsed['received_date']
                )
                
                if email_id:
                    # Get all active groups
                    active_groups = self.database.get_active_groups()
                    
                    for group in active_groups:
                        # Check if email should be sent to this group
                        if self.should_send_to_group(group, email_data['account_label']):
                            # Check if already sent to this group
                            if not self.database.email_sent_to_group(email_id, group['id']):
                                # Prepare notification data
                                notification_data = {
                                    'email_id': email_id,
                                    'account_label': email_data['account_label'],
                                    'account_email': email_data['account_email'],
                                    'sender': parsed['sender'],
                                    'subject': parsed['subject'],
                                    'body_preview': parsed['body_preview']
                                }
                                
                                # Send notification (run in event loop)
                                loop = asyncio.new_event_loop()
                                asyncio.set_event_loop(loop)
                                
                                telegram_message_id = loop.run_until_complete(
                                    self.send_email_notification(
                                        notification_data, 
                                        group['id'], 
                                        group['chat_id']
                                    )
                                )
                                
                                loop.close()
                                
                                if telegram_message_id:
                                    logger.info(f"Sent notification to group {group['chat_title']}: {parsed['subject']}")
                
            except Exception as e:
                if self.running:  # Only log if not shutting down
                    logger.error(f"Error processing email queue: {e}")
        
        logger.info("Email queue processor stopped")
    
    async def initialize(self):
        """Initialize the bot"""
        # Create application
        self.application = Application.builder().token(self.settings.telegram_bot_token).build()
        self.bot = self.application.bot
        
        # Add handlers
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("subscribe", self.subscribe_command))
        self.application.add_handler(CommandHandler("unsubscribe", self.unsubscribe_command))
        self.application.add_handler(CommandHandler("filter", self.filter_command))
        self.application.add_handler(CommandHandler("status", self.status_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_read_button))
        
        # Initialize application
        await self.application.initialize()
        await self.application.start()
        
        logger.info("Telegram bot initialized")
    
    async def start(self):
        """Start the bot"""
        self.running = True
        
        # Start email queue processor in separate thread
        self.process_thread = threading.Thread(target=self.process_email_queue)
        self.process_thread.daemon = True
        self.process_thread.start()
        
        # Start polling
        await self.application.updater.start_polling()
        
        logger.info("Telegram bot started")
    
    async def stop(self):
        """Stop the bot"""
        logger.info("Stopping Telegram bot")
        
        self.running = False
        
        # Stop the processor thread
        if self.process_thread:
            self.process_thread.join(timeout=5)
        
        # Stop the application
        if self.application:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
        
        logger.info("Telegram bot stopped")
    
    async def run(self):
        """Run the bot (blocking)"""
        await self.initialize()
        await self.start()
        
        # Keep running until interrupted
        try:
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            await self.stop()