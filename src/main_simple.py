#!/usr/bin/env python3

import asyncio
import logging
import signal
import sys
from queue import Queue
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings
from src.bot_simple import TelegramBot
from src.imap_watcher import EmailWatcherManager

logger = logging.getLogger(__name__)

class EmailNotifierApp:
    def __init__(self):
        self.settings = get_settings()
        self.email_queue = Queue()
        self.watcher_manager = EmailWatcherManager(
            self.email_queue,
            self.settings.check_interval
        )
        self.telegram_bot = TelegramBot(
            self.settings,
            self.email_queue
        )
        self.shutdown_event = threading.Event()
    
    def setup_signal_handlers(self):
        """Setup signal handlers"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}")
            self.shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    def validate_configuration(self):
        """Validate configuration"""
        if not self.settings.email_accounts:
            logger.error("No email accounts configured")
            sys.exit(1)
        
        logger.info(f"Configuration OK:")
        logger.info(f"  - Bot token: ✓")
        logger.info(f"  - Email accounts: {len(self.settings.email_accounts)}")
        
        for account in self.settings.email_accounts:
            logger.info(f"  - Account: {account.label} ({account.email})")
    
    def setup_email_watchers(self):
        """Setup email watchers"""
        for account_config in self.settings.email_accounts:
            self.watcher_manager.add_account(account_config.model_dump())
        
        logger.info(f"Configured {len(self.settings.email_accounts)} email watchers")
    
    async def run_bot(self):
        """Run Telegram bot"""
        try:
            await self.telegram_bot.initialize()
            await self.telegram_bot.start()
            
            # Wait for shutdown
            while not self.shutdown_event.is_set():
                await asyncio.sleep(1)
            
            await self.telegram_bot.stop()
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            self.shutdown_event.set()
    
    def run(self):
        """Main entry point"""
        logger.info("=" * 50)
        logger.info("Email Notifier Starting (Simple Version)")
        logger.info("=" * 50)
        
        self.validate_configuration()
        self.setup_signal_handlers()
        self.setup_email_watchers()
        
        # Start email watchers
        self.watcher_manager.start_all()
        
        # Run bot
        try:
            asyncio.run(self.run_bot())
        except KeyboardInterrupt:
            logger.info("Interrupted")
        finally:
            self.watcher_manager.stop_all()
            
            logger.info("=" * 50)
            logger.info("Email Notifier Stopped")
            logger.info("=" * 50)

def main():
    """Main"""
    try:
        app = EmailNotifierApp()
        app.run()
    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()