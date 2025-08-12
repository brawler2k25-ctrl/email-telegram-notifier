import sqlite3
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple
from contextlib import contextmanager
import hashlib

logger = logging.getLogger(__name__)

class EmailDatabase:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Create emails table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS emails (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    email_account TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    body_preview TEXT,
                    received_date TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    email_hash TEXT NOT NULL
                )
            """)
            
            # Create groups table for managing subscriptions
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER UNIQUE NOT NULL,
                    chat_title TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    filter_accounts TEXT,  -- JSON list of account labels to filter (null = all)
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    added_by INTEGER,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create email_notifications table for tracking messages per group
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS email_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email_id INTEGER NOT NULL,
                    group_id INTEGER NOT NULL,
                    telegram_message_id INTEGER,
                    is_handled BOOLEAN DEFAULT 0,
                    handled_at TIMESTAMP,
                    handled_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (email_id) REFERENCES emails(id),
                    FOREIGN KEY (group_id) REFERENCES groups(id),
                    UNIQUE(email_id, group_id)
                )
            """)
            
            # Create indexes for better performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_message_id ON emails(message_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_hash ON emails(email_hash)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_id ON groups(chat_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_notifications_email ON email_notifications(email_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_email_notifications_group ON email_notifications(group_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_telegram_msg_id ON email_notifications(telegram_message_id)
            """)
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def generate_email_hash(self, message_id: str, sender: str, subject: str) -> str:
        """Generate a unique hash for an email to prevent duplicates"""
        content = f"{message_id}|{sender}|{subject}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    def email_exists(self, message_id: str, sender: str, subject: str) -> bool:
        """Check if an email already exists in the database"""
        email_hash = self.generate_email_hash(message_id, sender, subject)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM emails 
                WHERE email_hash = ? OR message_id = ?
            """, (email_hash, message_id))
            result = cursor.fetchone()
            return result['count'] > 0
    
    def add_email(
        self,
        message_id: str,
        email_account: str,
        sender: str,
        subject: str,
        body_preview: str,
        received_date: datetime
    ) -> Optional[int]:
        """Add a new email to the database"""
        email_hash = self.generate_email_hash(message_id, sender, subject)
        
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # Check if email already exists
                cursor.execute("SELECT id FROM emails WHERE email_hash = ?", (email_hash,))
                existing = cursor.fetchone()
                if existing:
                    return existing['id']
                
                cursor.execute("""
                    INSERT INTO emails (
                        message_id, email_account, sender, subject, 
                        body_preview, received_date, email_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    message_id, email_account, sender, subject,
                    body_preview, received_date, email_hash
                ))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding email to database: {e}")
            return None
    
    # Group management methods
    def add_group(self, chat_id: int, chat_title: str, added_by: int, filter_accounts: List[str] = None) -> Optional[int]:
        """Add a new group subscription"""
        import json
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                filter_json = json.dumps(filter_accounts) if filter_accounts else None
                cursor.execute("""
                    INSERT OR REPLACE INTO groups (chat_id, chat_title, added_by, filter_accounts)
                    VALUES (?, ?, ?, ?)
                """, (chat_id, chat_title, added_by, filter_json))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding group: {e}")
            return None
    
    def remove_group(self, chat_id: int) -> bool:
        """Remove a group subscription"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE groups SET is_active = 0 WHERE chat_id = ?", (chat_id,))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error removing group: {e}")
            return False
    
    def get_active_groups(self) -> List[dict]:
        """Get all active group subscriptions"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups WHERE is_active = 1")
            return [dict(row) for row in cursor.fetchall()]
    
    def get_group_by_chat_id(self, chat_id: int) -> Optional[dict]:
        """Get group info by chat ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM groups WHERE chat_id = ?", (chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def update_group_filter(self, chat_id: int, filter_accounts: List[str] = None) -> bool:
        """Update account filter for a group"""
        import json
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                filter_json = json.dumps(filter_accounts) if filter_accounts else None
                cursor.execute("""
                    UPDATE groups 
                    SET filter_accounts = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE chat_id = ?
                """, (filter_json, chat_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error updating group filter: {e}")
            return False
    
    # Email notification methods
    def add_notification(self, email_id: int, group_id: int, telegram_message_id: int) -> Optional[int]:
        """Add email notification for a specific group"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO email_notifications 
                    (email_id, group_id, telegram_message_id)
                    VALUES (?, ?, ?)
                """, (email_id, group_id, telegram_message_id))
                conn.commit()
                return cursor.lastrowid
        except Exception as e:
            logger.error(f"Error adding notification: {e}")
            return None
    
    def mark_notification_handled(self, telegram_message_id: int, handled_by: int) -> bool:
        """Mark a notification as handled"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE email_notifications 
                    SET is_handled = 1, handled_at = CURRENT_TIMESTAMP, handled_by = ?
                    WHERE telegram_message_id = ? AND is_handled = 0
                """, (handled_by, telegram_message_id))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error marking notification as handled: {e}")
            return False
    
    def email_sent_to_group(self, email_id: int, group_id: int) -> bool:
        """Check if email was already sent to a specific group"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM email_notifications 
                WHERE email_id = ? AND group_id = ?
            """, (email_id, group_id))
            result = cursor.fetchone()
            return result['count'] > 0
    
    def get_group_stats(self, chat_id: int) -> dict:
        """Get statistics for a specific group"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    g.id as group_id,
                    COUNT(DISTINCT en.id) as total_notifications,
                    SUM(CASE WHEN en.is_handled = 1 THEN 1 ELSE 0 END) as handled,
                    SUM(CASE WHEN en.is_handled = 0 THEN 1 ELSE 0 END) as unhandled
                FROM groups g
                LEFT JOIN email_notifications en ON g.id = en.group_id
                WHERE g.chat_id = ?
                GROUP BY g.id
            """, (chat_id,))
            row = cursor.fetchone()
            return dict(row) if row else {"total_notifications": 0, "handled": 0, "unhandled": 0}
    
    def cleanup_old_handled_notifications(self, days: int = 30):
        """Clean up old handled notifications"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Clean up old notifications
            cursor.execute("""
                DELETE FROM email_notifications 
                WHERE is_handled = 1 
                AND handled_at < datetime('now', '-' || ? || ' days')
            """, (days,))
            deleted_notifications = cursor.rowcount
            
            # Clean up orphaned emails (no notifications referencing them)
            cursor.execute("""
                DELETE FROM emails 
                WHERE id NOT IN (SELECT DISTINCT email_id FROM email_notifications)
                AND created_at < datetime('now', '-' || ? || ' days')
            """, (days,))
            deleted_emails = cursor.rowcount
            
            conn.commit()
            if deleted_notifications > 0 or deleted_emails > 0:
                logger.info(f"Cleaned up {deleted_notifications} old notifications and {deleted_emails} orphaned emails")
    
    def get_overall_stats(self) -> dict:
        """Get overall database statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    (SELECT COUNT(*) FROM emails) as total_emails,
                    (SELECT COUNT(*) FROM groups WHERE is_active = 1) as active_groups,
                    (SELECT COUNT(*) FROM email_notifications) as total_notifications,
                    (SELECT COUNT(*) FROM email_notifications WHERE is_handled = 1) as handled_notifications
            """)
            row = cursor.fetchone()
            return dict(row) if row else {
                "total_emails": 0, 
                "active_groups": 0, 
                "total_notifications": 0,
                "handled_notifications": 0
            }