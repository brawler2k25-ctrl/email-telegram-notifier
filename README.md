# Corporate Email → Telegram Notifier

A Python 3.11 application that monitors multiple corporate email accounts via IMAP and sends notifications to a Telegram group chat. Team members can mark emails as "read" to remove them from the chat for everyone.

## Features

- ✅ **Multi-Account Support**: Monitor multiple email accounts simultaneously
- ✅ **Real-time Notifications**: IMAP IDLE support for instant notifications (falls back to polling)
- ✅ **Spam Filtering**: Automatically ignores spam, auto-replies, and no-reply emails
- ✅ **Duplicate Prevention**: SQLite database ensures no duplicate notifications
- ✅ **Team Collaboration**: "Read ✅" button removes message for all team members
- ✅ **Clean Email Preview**: Extracts text from HTML emails, limited to 600 characters
- ✅ **Docker Support**: Easy deployment with Docker and docker-compose
- ✅ **Secure**: Supports SSL/TLS connections and user authorization

## Project Structure

```
email-telegram-notifier/
├── src/
│   ├── main.py           # Application entry point
│   ├── config.py         # Configuration management
│   ├── imap_watcher.py   # Email monitoring logic
│   ├── parser.py         # Email parsing and cleaning
│   ├── bot.py           # Telegram bot functionality
│   └── db.py            # Database operations
├── accounts.yaml         # Email accounts configuration
├── .env.example         # Environment variables template
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container definition
├── docker-compose.yml  # Docker orchestration
└── README.md          # This file
```

## Prerequisites

- Docker and Docker Compose (for containerized deployment)
- OR Python 3.11+ (for local development)
- Telegram Bot Token
- Telegram Group Chat ID
- Email account credentials with IMAP access

## Setup Instructions

### 1. Create a Telegram Bot

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the instructions
3. Save the bot token provided by BotFather
4. Add the bot to your group chat as an administrator

### 2. Get Your Telegram Chat ID

Method 1: Using the bot (after adding to group)
1. Send any message in the group
2. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
3. Look for `"chat":{"id":-1234567890}` - this is your chat ID (negative for groups)

Method 2: Using @userinfobot
1. Add `@userinfobot` to your group
2. The bot will display the chat ID
3. Remove the bot after getting the ID

### 3. Configure Email Accounts

1. Copy the example environment file:
```bash
cp .env.example .env
```

2. Edit `.env` with your configuration:
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=-1001234567890
TELEGRAM_ALLOWED_USERS=123456789,987654321  # Optional: restrict to specific users
DATABASE_PATH=data/emails.db
CHECK_INTERVAL=60
LOG_LEVEL=INFO
```

3. Edit `accounts.yaml` with your email accounts:
```yaml
accounts:
  - label: "Main Office"
    email: "office@company.com"
    password: "your_app_password"  # Use app-specific password for Gmail/Outlook
    imap_server: "imap.gmail.com"
    imap_port: 993
    use_ssl: true
    use_idle: true
```

### 4. Email Provider Settings

#### Gmail
1. Enable 2-factor authentication
2. Generate an app-specific password: https://myaccount.google.com/apppasswords
3. Use `imap.gmail.com` as the IMAP server

#### Outlook/Office 365
1. Use `outlook.office365.com` as the IMAP server
2. May require app-specific password if 2FA is enabled

#### Other Providers
- Check your email provider's documentation for IMAP settings
- Ensure IMAP is enabled in your email account settings

## Running with Docker

### Quick Start

1. Clone the repository:
```bash
git clone <repository-url>
cd email-telegram-notifier
```

2. Configure your settings (see Setup Instructions above)

3. Build and run:
```bash
docker-compose up -d
```

4. View logs:
```bash
docker-compose logs -f
```

5. Stop the service:
```bash
docker-compose down
```

### Docker Commands

```bash
# Build the image
docker-compose build

# Start in background
docker-compose up -d

# View logs
docker-compose logs -f email-notifier

# Restart the service
docker-compose restart

# Stop and remove containers
docker-compose down

# Stop and remove everything including volumes
docker-compose down -v
```

## Running Locally (Development)

1. Create a virtual environment:
```bash
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python src/main.py
```

## Usage

Once running, the bot will:

1. Connect to all configured email accounts
2. Monitor for new emails (using IDLE or polling)
3. Send notifications to the Telegram group for each new email
4. Each notification includes:
   - Email account label and address
   - Sender information
   - Subject line
   - Preview of the email body (max 600 characters)
   - "Read ✅" button

### Bot Commands

- `/start` - Welcome message and statistics
- `/status` - Current bot status and email statistics

### Managing Notifications

- Click "Read ✅" on any email notification
- The message will be deleted for all group members
- The email will be marked as handled in the database
- No duplicate notifications will be sent for that email

## Security Considerations

1. **Use App-Specific Passwords**: Never use your main email password
2. **Secure Your .env File**: Never commit `.env` to version control
3. **Restrict User Access**: Use `TELEGRAM_ALLOWED_USERS` to limit who can use the bot
4. **Use SSL/TLS**: Always enable SSL for email connections
5. **Regular Updates**: Keep dependencies updated for security patches

## Troubleshooting

### Bot not receiving messages
- Ensure the bot is added as an administrator in the group
- Check that the chat ID is correct (should be negative for groups)
- Verify the bot token is valid

### Email connection failures
- Verify IMAP is enabled in your email settings
- Check firewall/network settings
- Ensure correct server address and port
- Try with `use_idle: false` if IDLE isn't supported

### High memory usage
- Adjust `CHECK_INTERVAL` for less frequent polling
- Limit the number of accounts being monitored
- Check Docker resource limits in `docker-compose.yml`

### Database issues
- Ensure the `data` directory has write permissions
- Check disk space availability
- Database is automatically created on first run

## Database Management

The SQLite database stores:
- Email message IDs (to prevent duplicates)
- Telegram message IDs (for deletion)  
- Email metadata (sender, subject, preview)
- Handled status and timestamp

Old handled emails are automatically cleaned up after 30 days.

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather | Required |
| `TELEGRAM_CHAT_ID` | Group chat ID (negative number) | Required |
| `TELEGRAM_ALLOWED_USERS` | Comma-separated user IDs | Optional |
| `DATABASE_PATH` | SQLite database location | `data/emails.db` |
| `CHECK_INTERVAL` | Email check interval (seconds) | `60` |
| `LOG_LEVEL` | Logging level | `INFO` |

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is provided as-is for educational and commercial use.

## Support

For issues, questions, or suggestions, please create an issue in the repository.