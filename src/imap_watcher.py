import logging
import time
import ssl
from typing import Optional, Callable, List
from datetime import datetime
import imapclient
from imapclient import IMAPClient
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import threading
from queue import Queue

logger = logging.getLogger(__name__)

class EmailWatcher:
    def __init__(
        self,
        account_config: dict,
        email_callback: Callable,
        check_interval: int = 60
    ):
        self.account = account_config
        self.email_callback = email_callback
        self.check_interval = check_interval
        self.client: Optional[IMAPClient] = None
        self.stop_event = threading.Event()
        self.last_seen_uids = set()
        self.thread: Optional[threading.Thread] = None
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((ConnectionError, ssl.SSLError))
    )
    def connect(self):
        """Connect to IMAP server with retry logic"""
        try:
            logger.info(f"Connecting to {self.account['email']} on {self.account['imap_server']}")
            
            # Create SSL context
            context = ssl.create_default_context()
            
            # Initialize IMAP client
            self.client = IMAPClient(
                self.account['imap_server'],
                port=self.account['imap_port'],
                use_uid=True,
                ssl=self.account['use_ssl'],
                ssl_context=context if self.account['use_ssl'] else None
            )
            
            # Login
            self.client.login(self.account['email'], self.account['password'])
            
            # Select INBOX
            self.client.select_folder('INBOX')
            
            # Get initial UIDs to avoid processing old emails
            messages = self.client.search(['ALL'])
            self.last_seen_uids = set(messages)
            
            logger.info(f"Successfully connected to {self.account['email']}")
            
        except Exception as e:
            logger.error(f"Failed to connect to {self.account['email']}: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from IMAP server"""
        if self.client:
            try:
                self.client.logout()
            except:
                pass
            self.client = None
    
    def check_new_emails(self) -> List[dict]:
        """Check for new emails"""
        new_emails = []
        
        try:
            if not self.client:
                self.connect()
            
            # Search for all messages
            messages = self.client.search(['ALL'])
            current_uids = set(messages)
            
            # Find new UIDs
            new_uids = current_uids - self.last_seen_uids
            
            if new_uids:
                logger.info(f"Found {len(new_uids)} new emails in {self.account['label']}")
                
                # Fetch new messages
                for uid in new_uids:
                    try:
                        # Fetch the email
                        response = self.client.fetch([uid], ['RFC822'])
                        if uid in response:
                            raw_email = response[uid][b'RFC822']
                            
                            # Process the email
                            email_data = {
                                'account_label': self.account['label'],
                                'account_email': self.account['email'],
                                'raw_email': raw_email,
                                'uid': uid
                            }
                            
                            new_emails.append(email_data)
                            
                    except Exception as e:
                        logger.error(f"Error fetching email {uid}: {e}")
                
                # Update last seen UIDs
                self.last_seen_uids = current_uids
            
        except (ConnectionError, ssl.SSLError, imapclient.exceptions.IMAPClientError) as e:
            logger.error(f"Connection error for {self.account['email']}: {e}")
            self.disconnect()
            # Will retry on next check
        except Exception as e:
            logger.error(f"Error checking emails for {self.account['email']}: {e}")
        
        return new_emails
    
    def idle_loop(self):
        """IMAP IDLE loop for real-time email notifications"""
        logger.info(f"Starting IDLE mode for {self.account['label']}")
        
        while not self.stop_event.is_set():
            try:
                if not self.client:
                    self.connect()
                
                # Start IDLE mode
                self.client.idle()
                
                # Wait for updates (with timeout for periodic checks)
                responses = self.client.idle_check(timeout=30)
                
                if responses:
                    # Exit IDLE mode to process new emails
                    self.client.idle_done()
                    
                    # Check for new emails
                    new_emails = self.check_new_emails()
                    for email_data in new_emails:
                        self.email_callback(email_data)
                else:
                    # Timeout reached, just refresh the connection
                    self.client.idle_done()
                    
                    # Send NOOP to keep connection alive
                    self.client.noop()
                
            except Exception as e:
                logger.error(f"IDLE error for {self.account['email']}: {e}")
                self.disconnect()
                time.sleep(10)  # Wait before reconnecting
    
    def polling_loop(self):
        """Polling loop for servers that don't support IDLE"""
        logger.info(f"Starting polling mode for {self.account['label']} (interval: {self.check_interval}s)")
        
        while not self.stop_event.is_set():
            try:
                # Check for new emails
                new_emails = self.check_new_emails()
                for email_data in new_emails:
                    self.email_callback(email_data)
                
                # Wait for next check
                self.stop_event.wait(self.check_interval)
                
            except Exception as e:
                logger.error(f"Polling error for {self.account['email']}: {e}")
                time.sleep(10)  # Wait before retrying
    
    def start(self):
        """Start watching for emails"""
        if self.thread and self.thread.is_alive():
            logger.warning(f"Watcher already running for {self.account['label']}")
            return
        
        self.stop_event.clear()
        
        # Choose IDLE or polling based on configuration
        if self.account.get('use_idle', True):
            # Try IDLE first
            try:
                self.connect()
                if self.client and hasattr(self.client, 'idle'):
                    self.thread = threading.Thread(
                        target=self.idle_loop,
                        name=f"IDLE-{self.account['label']}"
                    )
                else:
                    logger.info(f"IDLE not supported for {self.account['label']}, falling back to polling")
                    self.thread = threading.Thread(
                        target=self.polling_loop,
                        name=f"Poll-{self.account['label']}"
                    )
            except Exception as e:
                logger.error(f"Failed to initialize watcher for {self.account['label']}: {e}")
                self.thread = threading.Thread(
                    target=self.polling_loop,
                    name=f"Poll-{self.account['label']}"
                )
        else:
            self.thread = threading.Thread(
                target=self.polling_loop,
                name=f"Poll-{self.account['label']}"
            )
        
        self.thread.daemon = True
        self.thread.start()
        logger.info(f"Started watcher for {self.account['label']}")
    
    def stop(self):
        """Stop watching for emails"""
        logger.info(f"Stopping watcher for {self.account['label']}")
        self.stop_event.set()
        
        if self.thread:
            self.thread.join(timeout=5)
        
        self.disconnect()
        logger.info(f"Stopped watcher for {self.account['label']}")


class EmailWatcherManager:
    """Manages multiple email watchers"""
    
    def __init__(self, email_queue: Queue, check_interval: int = 60):
        self.email_queue = email_queue
        self.check_interval = check_interval
        self.watchers: List[EmailWatcher] = []
    
    def add_account(self, account_config: dict):
        """Add an email account to watch"""
        def email_callback(email_data):
            self.email_queue.put(email_data)
        
        watcher = EmailWatcher(
            account_config=account_config,
            email_callback=email_callback,
            check_interval=self.check_interval
        )
        
        self.watchers.append(watcher)
        return watcher
    
    def start_all(self):
        """Start all watchers"""
        logger.info(f"Starting {len(self.watchers)} email watchers")
        for watcher in self.watchers:
            try:
                watcher.start()
            except Exception as e:
                logger.error(f"Failed to start watcher: {e}")
    
    def stop_all(self):
        """Stop all watchers"""
        logger.info("Stopping all email watchers")
        for watcher in self.watchers:
            try:
                watcher.stop()
            except Exception as e:
                logger.error(f"Failed to stop watcher: {e}")
    
    def get_status(self) -> dict:
        """Get status of all watchers"""
        status = {
            'total': len(self.watchers),
            'active': sum(1 for w in self.watchers if w.thread and w.thread.is_alive()),
            'accounts': [
                {
                    'label': w.account['label'],
                    'email': w.account['email'],
                    'active': w.thread.is_alive() if w.thread else False
                }
                for w in self.watchers
            ]
        }
        return status