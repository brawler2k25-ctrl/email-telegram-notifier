import os
import yaml
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv
import logging

load_dotenv()

class EmailAccount(BaseModel):
    label: str
    email: str
    password: str
    imap_server: str
    imap_port: int = 993
    use_ssl: bool = True
    use_idle: bool = True
    
    @validator('label')
    def validate_label(cls, v):
        if not v or not v.strip():
            raise ValueError("Account label cannot be empty")
        return v.strip()

class Settings(BaseModel):
    telegram_bot_token: str
    telegram_chat_id: int
    telegram_allowed_users: Optional[List[int]] = Field(default_factory=list)
    database_path: Path = Path("data/emails.db")
    check_interval: int = 60
    log_level: str = "INFO"
    email_accounts: List[EmailAccount] = Field(default_factory=list)
    
    max_preview_length: int = 600
    spam_keywords: List[str] = Field(default_factory=lambda: [
        "unsubscribe", "no-reply", "noreply", "auto-reply", "automatic reply",
        "out of office", "vacation", "away from office"
    ])
    
    @validator('telegram_bot_token')
    def validate_bot_token(cls, v):
        if not v or v == "your_bot_token_here":
            raise ValueError("Please set a valid TELEGRAM_BOT_TOKEN in .env file")
        return v
    
    @validator('telegram_chat_id')
    def validate_chat_id(cls, v):
        if v == -1001234567890:
            raise ValueError("Please set a valid TELEGRAM_CHAT_ID in .env file")
        return v
    
    @validator('log_level')
    def validate_log_level(cls, v):
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}")
        return v.upper()

def load_settings() -> Settings:
    """Load settings from environment variables and accounts.yaml"""
    
    # Load accounts from YAML
    accounts_file = Path("accounts.yaml")
    email_accounts = []
    
    if accounts_file.exists():
        with open(accounts_file, 'r') as f:
            accounts_data = yaml.safe_load(f)
            if accounts_data and 'accounts' in accounts_data:
                for acc in accounts_data['accounts']:
                    email_accounts.append(EmailAccount(**acc))
    else:
        logging.warning("accounts.yaml not found. No email accounts configured.")
    
    # Parse allowed users from comma-separated string
    allowed_users_str = os.getenv("TELEGRAM_ALLOWED_USERS", "")
    allowed_users = []
    if allowed_users_str:
        try:
            allowed_users = [int(uid.strip()) for uid in allowed_users_str.split(",") if uid.strip()]
        except ValueError:
            logging.error("Invalid TELEGRAM_ALLOWED_USERS format. Must be comma-separated integers.")
    
    settings = Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=int(os.getenv("TELEGRAM_CHAT_ID", "-1001234567890")),
        telegram_allowed_users=allowed_users,
        database_path=Path(os.getenv("DATABASE_PATH", "data/emails.db")),
        check_interval=int(os.getenv("CHECK_INTERVAL", "60")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        email_accounts=email_accounts
    )
    
    # Setup logging
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create data directory if it doesn't exist
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    
    return settings

# Global settings instance
settings = None

def get_settings() -> Settings:
    """Get or create settings singleton"""
    global settings
    if settings is None:
        settings = load_settings()
    return settings