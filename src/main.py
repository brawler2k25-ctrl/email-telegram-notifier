#!/usr/bin/env python3

import asyncio
import logging
import signal
import sys
from queue import Queue
import threading
from pathlib import Path

# Add parent directory to path for imports when running directly
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.db import EmailDatabase
from src.bot import TelegramBot
from src.imap_watcher import EmailWatcherManager

logger = logging.getLogger(__name__)

class EmailNotifierApp:
    def __init__(self):
        self.settings = get_settings()
        self.database = EmailDatabase(self.settings.database_path)
        self.email_queue = Queue()
        self.watcher_manager = EmailWatcherManager(
            self.email_queue,
            self.settings.check_interval
        )
        self.telegram_bot = TelegramBot(
            self.settings,
            self.database,
            self.email_queue
        )
        self.shutdown_event = threading.Event()
    
    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating shutdown...")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def validate_configuration(self):
        """Validate that all required configuration is present"""
        if not self.settings.email_accounts:
            logger.error("No email accounts configured in accounts.yaml")
            sys.exit(1)
        
        logger.info(f"Configuration validated:")
        logger.info(f"  - Bot token: {'✓' if self.settings.telegram_bot_token else '✗'}")
        logger.info(f"  - Chat ID: {self.settings.telegram_chat_id}")
        logger.info(f"  - Email accounts: {len(self.settings.email_accounts)}")
        logger.info(f"  - Database path: {self.settings.database_path}")
        
        for account in self.settings.email_accounts:
            logger.info(f"  - Account: {account.label} ({account.email})")
    
    def setup_email_watchers(self):
        """Setup email watchers for all configured accounts"""
        for account_config in self.settings.email_accounts:
            self.watcher_manager.add_account(account_config.dict())
        
        logger.info(f"Configured {len(self.settings.email_accounts)} email watchers")
    
    async def run_bot(self):
        """Run the Telegram bot"""
        try:
            await self.telegram_bot.initialize()
            await self.telegram_bot.start()
            
            # Send startup message
            try:
                await self.telegram_bot.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text="🚀 Email Notifier Bot started successfully!\n"
                         f"Monitoring {len(self.settings.email_accounts)} email accounts."
                )
            except Exception as e:
                logger.warning(f"Could not send startup message: {e}")
            
            # Wait for shutdown signal
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1)
            
            # Send shutdown message
            try:
                await self.telegram_bot.bot.send_message(
                    chat_id=self.settings.telegram_chat_id,
                    text="🛑 Email Notifier Bot is shutting down..."
                )
            except Exception as e:
                logger.warning(f"Could not send shutdown message: {e}")
            
            await self.telegram_bot.stop()
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            self.shutdown_event.set()
    
    def run(self):
        """Main application entry point"""
        logger.info("=" * 50)
        logger.info("Email → Telegram Notifier Starting")
        logger.info("=" * 50)
        
        # Validate configuration
        self.validate_configuration()
        
        # Setup signal handlers
        self.setup_signal_handlers()
        
        # Setup email watchers
        self.setup_email_watchers()
        
        # Start email watchers
        self.watcher_manager.start_all()
        
        # Cleanup old handled notifications (older than 30 days)
        self.database.cleanup_old_handled_notifications(days=30)
        
        # Run the bot in asyncio event loop
        try:
            asyncio.run(self.run_bot())
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            # Stop email watchers
            self.watcher_manager.stop_all()
            
            logger.info("=" * 50)
            logger.info("Email → Telegram Notifier Stopped")
            logger.info("=" * 50)


def main():
    """Main entry point"""
    try:
        app = EmailNotifierApp()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()