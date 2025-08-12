import re
import logging
from typing import Optional, Tuple
from bs4 import BeautifulSoup
import mailparser
from email.message import Message
from datetime import datetime

logger = logging.getLogger(__name__)

class EmailParser:
    def __init__(self, max_preview_length: int = 600, spam_keywords: list = None):
        self.max_preview_length = max_preview_length
        self.spam_keywords = [kw.lower() for kw in (spam_keywords or [])]
    
    def parse_email(self, raw_email: bytes) -> Optional[dict]:
        """Parse raw email and extract relevant information"""
        try:
            mail = mailparser.parse_from_bytes(raw_email)
            
            # Extract basic information
            message_id = mail.message_id or ""
            sender = self._extract_sender(mail)
            subject = mail.subject or "No Subject"
            date = self._parse_date(mail.date)
            
            # Extract and clean body
            body_text = self._extract_body_text(mail)
            body_preview = self._create_preview(body_text)
            
            return {
                'message_id': message_id,
                'sender': sender,
                'subject': subject,
                'body_preview': body_preview,
                'received_date': date,
                'is_spam': self._is_spam(sender, subject, body_text)
            }
        except Exception as e:
            logger.error(f"Error parsing email: {e}")
            return None
    
    def _extract_sender(self, mail) -> str:
        """Extract sender name and email"""
        if mail.from_:
            if isinstance(mail.from_, list) and mail.from_:
                sender_info = mail.from_[0]
            else:
                sender_info = mail.from_
            
            if isinstance(sender_info, tuple) and len(sender_info) == 2:
                name, email = sender_info
                if name:
                    return f"{name} <{email}>"
                return email
            elif isinstance(sender_info, str):
                return sender_info
        
        return "Unknown Sender"
    
    def _parse_date(self, date_obj) -> datetime:
        """Parse email date to datetime object"""
        if isinstance(date_obj, datetime):
            return date_obj
        elif isinstance(date_obj, str):
            try:
                # Try to parse various date formats
                from email.utils import parsedate_to_datetime
                return parsedate_to_datetime(date_obj)
            except:
                pass
        
        # Return current time if parsing fails
        return datetime.now()
    
    def _extract_body_text(self, mail) -> str:
        """Extract and clean email body text"""
        body_text = ""
        
        # Try to get plain text first
        if mail.text_plain:
            if isinstance(mail.text_plain, list):
                body_text = "\n".join(mail.text_plain)
            else:
                body_text = mail.text_plain
        
        # If no plain text, try to extract from HTML
        elif mail.text_html:
            if isinstance(mail.text_html, list):
                html_text = "\n".join(mail.text_html)
            else:
                html_text = mail.text_html
            
            body_text = self._html_to_text(html_text)
        
        # Clean up the text
        body_text = self._clean_text(body_text)
        
        return body_text
    
    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get text and preserve some structure
            lines = []
            for elem in soup.stripped_strings:
                lines.append(elem)
            
            text = "\n".join(lines)
            
            # Clean up excessive whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)
            
            return text
        except Exception as e:
            logger.error(f"Error converting HTML to text: {e}")
            return ""
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n', '\n\n', text)
        
        # Remove email signatures (common patterns)
        signature_patterns = [
            r'--\s*\n.*',  # Standard email signature delimiter
            r'Sent from my.*',
            r'Get Outlook for.*',
            r'This email and any attachments.*',
            r'CONFIDENTIAL.*',
            r'This message contains.*confidential.*'
        ]
        
        for pattern in signature_patterns:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.DOTALL)
        
        # Trim whitespace
        text = text.strip()
        
        return text
    
    def _create_preview(self, text: str) -> str:
        """Create a preview of the email body"""
        if not text:
            return "No content"
        
        # Remove URLs to save space in preview
        text = re.sub(r'https?://\S+', '[URL]', text)
        
        # Truncate to max length
        if len(text) > self.max_preview_length:
            text = text[:self.max_preview_length - 3] + "..."
        
        return text
    
    def _is_spam(self, sender: str, subject: str, body: str) -> bool:
        """Check if email is spam or auto-reply"""
        combined_text = f"{sender} {subject} {body}".lower()
        
        # Check for spam keywords
        for keyword in self.spam_keywords:
            if keyword in combined_text:
                logger.debug(f"Email marked as spam due to keyword: {keyword}")
                return True
        
        # Check for auto-reply patterns in headers
        auto_reply_patterns = [
            r'auto.?reply',
            r'automatic.?reply',
            r'out.?of.?office',
            r'vacation.?reply',
            r'away.?from.?office',
            r'be.?back.?on'
        ]
        
        for pattern in auto_reply_patterns:
            if re.search(pattern, combined_text, re.IGNORECASE):
                logger.debug(f"Email marked as auto-reply")
                return True
        
        # Check for no-reply addresses
        if re.search(r'no.?reply|donotreply|postmaster|mailer.?daemon', sender.lower()):
            logger.debug(f"Email marked as spam due to no-reply sender")
            return True
        
        return False
    
    def format_telegram_message(
        self,
        account_label: str,
        account_email: str,
        sender: str,
        subject: str,
        body_preview: str
    ) -> str:
        """Format email for Telegram message"""
        # Escape special characters for Telegram MarkdownV2
        def escape_markdown(text):
            # List of characters to escape in MarkdownV2
            escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
            for char in escape_chars:
                text = text.replace(char, f'\\{char}')
            return text
        
        # Format the message
        message = f"📧 *New Email*\n\n"
        message += f"📬 *Inbox:* {escape_markdown(account_label)} \\({escape_markdown(account_email)}\\)\n"
        message += f"👤 *From:* {escape_markdown(sender)}\n"
        message += f"📝 *Subject:* {escape_markdown(subject)}\n\n"
        message += f"📄 *Preview:*\n{escape_markdown(body_preview)}"
        
        return message