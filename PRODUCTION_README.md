# 🚀 Production-Ready Telegram Bot

This is a production-enhanced version of the Telegram bot with advanced features for reliability, scalability, and security.

## 🌟 Production Features

### 🔧 Core Enhancements
- **MongoDB Integration**: Persistent user data, download history, and system statistics
- **Advanced Download Manager**: Queue-based processing with retry mechanisms
- **Circuit Breaker Pattern**: Automatic failure handling for external services
- **Rate Limiting**: Per-user and global request limiting
- **Resource Monitoring**: Real-time system resource tracking
- **Security Layer**: Input sanitization, authentication, and suspicious activity detection

### 📊 New Commands
- `/pro_enhanced` - Enhanced download command with queue management
- `/status` - Real-time system and user statistics
- `/cleanup` - Manual cleanup of old files and data
- `/set_target` - Set target chat for uploads (from original)
- `/login_classplus` - Classplus authentication (from original)

### 🛡️ Security Features
- **Rate Limiting**: 10 requests/minute per user, 50 global requests/minute
- **Input Sanitization**: All user inputs are sanitized and validated
- **Suspicious Activity Detection**: Automatic detection of unusual patterns
- **User Blocking**: Automatic blocking for security violations
- **Secure Password Hashing**: PBKDF2 with SHA-256 for password storage

### 📈 Monitoring & Analytics
- **Real-time Statistics**: User activity, download success rates, system resources
- **Download History**: Complete history of all downloads with metadata
- **System Health Monitoring**: Memory, disk, CPU usage tracking
- **Automatic Cleanup**: Old files and data are automatically cleaned up

## 🔧 Installation & Setup

### Prerequisites
- Python 3.11+
- MongoDB (local or cloud)
- Debian/Ubuntu VM with at least 2GB RAM

### 1. Install Dependencies
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv git curl wget ffmpeg aria2 -y

# Install MongoDB (optional - can use cloud MongoDB)
sudo apt install mongodb -y
sudo systemctl start mongodb
sudo systemctl enable mongodb
```

### 2. Clone and Setup
```bash
git clone https://github.com/z89pro/DRM-Bot-2-zPRO.git
cd DRM-Bot-2-zPRO
git checkout codegen-bot/comprehensive-fixes-pr2

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Environment Configuration
Create `.env` file:
```bash
# Bot Configuration
BOT_TOKEN=your_bot_token_here
API_ID=your_api_id
API_HASH=your_api_hash

# User Authentication
AUTH_USERS=your_user_id_here
GROUPS=your_group_id_here  # Optional

# Database
MONGO_URI=mongodb://localhost:27017  # Or your MongoDB cloud URI
MONGO_DB_NAME=telegram_bot

# Optional Logging
LOG_CH=your_log_channel_id  # Optional

# Download Settings
DOWNLOAD_LOCATION=/home/$(whoami)/downloads

# Security Settings (Optional)
MAX_REQUESTS_PER_MINUTE=10
MAX_REQUESTS_PER_HOUR=100
MAX_GLOBAL_REQUESTS_PER_MINUTE=50
ADMIN_USERS=your_admin_user_id
```

### 4. Run the Bot
```bash
# Test run
source venv/bin/activate
python3 main.py

# Production run with systemd
sudo nano /etc/systemd/system/telegram-bot.service
```

Systemd service configuration:
```ini
[Unit]
Description=Production Telegram Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/home/your_username/DRM-Bot-2-zPRO
Environment=PATH=/home/your_username/DRM-Bot-2-zPRO/venv/bin
ExecStart=/home/your_username/DRM-Bot-2-zPRO/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot.service
sudo systemctl start telegram-bot.service
sudo systemctl status telegram-bot.service
```

## 📱 Usage Guide

### Basic Commands
- `/start` - Start the bot
- `/help` - Show all available commands
- `/pro_enhanced` - Enhanced download with queue management
- `/status` - Check system status and your statistics
- `/set_target` - Set target chat for uploads
- `/cleanup` - Clean up old files and data

### Enhanced Features
1. **Queue-based Downloads**: Files are processed in a queue with retry mechanisms
2. **Real-time Progress**: Live updates on download progress
3. **Automatic Cleanup**: Files are automatically deleted after upload
4. **User Statistics**: Track your download history and success rates
5. **Resource Monitoring**: System automatically manages resources

### User Limits
- **Daily Downloads**: 50 files per user per day
- **Rate Limiting**: 10 requests per minute per user
- **File Retention**: Files are kept for 24 hours maximum
- **History Retention**: Download history kept for 30 days

## 🔍 Monitoring & Maintenance

### View Logs
```bash
# Real-time logs
sudo journalctl -u telegram-bot.service -f

# Recent logs
sudo journalctl -u telegram-bot.service --since "1 hour ago"
```

### System Monitoring
```bash
# Check system resources
htop

# Check disk usage
df -h

# Check bot status
sudo systemctl status telegram-bot.service
```

### Database Management
```bash
# Connect to MongoDB
mongo

# Show databases
show dbs

# Use bot database
use telegram_bot

# Show collections
show collections

# View user statistics
db.users.find().pretty()

# View system statistics
db.system_stats.find().sort({timestamp: -1}).limit(10).pretty()
```

### Maintenance Commands
```bash
# Restart bot
sudo systemctl restart telegram-bot.service

# Update bot
cd DRM-Bot-2-zPRO
git pull origin codegen-bot/comprehensive-fixes-pr2
sudo systemctl restart telegram-bot.service

# Clean up manually
rm -rf DOWNLOADS/*
```

## 🚨 Troubleshooting

### Common Issues

**1. Bot not responding:**
```bash
# Check logs
sudo journalctl -u telegram-bot.service -n 50

# Check environment variables
env | grep BOT_TOKEN
```

**2. Database connection errors:**
```bash
# Check MongoDB status
sudo systemctl status mongodb

# Test connection
mongo --eval "db.adminCommand('ping')"
```

**3. High resource usage:**
```bash
# Check system resources
free -h
df -h

# Restart bot to clear memory
sudo systemctl restart telegram-bot.service
```

**4. Download failures:**
- Check if Classplus tokens are expired
- Verify network connectivity
- Check disk space availability

### Performance Optimization

**1. Increase concurrent downloads:**
Edit `core/download_manager.py`:
```python
download_manager = EnhancedDownloadManager(max_concurrent_downloads=5)
```

**2. Adjust cleanup intervals:**
Edit background tasks in `main.py`:
```python
await asyncio.sleep(1800)  # 30 minutes instead of 1 hour
```

**3. Database optimization:**
```bash
# Create additional indexes
mongo telegram_bot --eval "db.download_jobs.createIndex({user_id: 1, status: 1})"
```

## 📊 Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram API  │    │   Security      │    │   Database      │
│                 │    │   Layer         │    │   (MongoDB)     │
└─────────┬───────┘    └─────────┬───────┘    └─────────┬───────┘
          │                      │                      │
          ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Main Bot Process                            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Command       │  │   Download      │  │   Upload        │  │
│  │   Handlers      │  │   Manager       │  │   Manager       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Background    │  │   Resource      │  │   Circuit       │  │
│  │   Tasks         │  │   Monitor       │  │   Breaker       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 🔐 Security Considerations

1. **Environment Variables**: Never commit `.env` file to version control
2. **Database Security**: Use authentication for MongoDB in production
3. **Network Security**: Use firewall to restrict access to necessary ports only
4. **Regular Updates**: Keep all dependencies updated
5. **Monitoring**: Monitor logs for suspicious activities
6. **Backup**: Regular backup of database and configuration

## 📈 Scaling Considerations

For high-traffic deployments:

1. **Database Scaling**: Use MongoDB replica sets or sharding
2. **Load Balancing**: Deploy multiple bot instances behind a load balancer
3. **Caching**: Implement Redis for session caching
4. **CDN**: Use CDN for file distribution
5. **Monitoring**: Implement comprehensive monitoring with Prometheus/Grafana

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## ⚠️ Disclaimer

This bot is for educational purposes. Ensure you comply with Telegram's Terms of Service and respect content creators' rights when downloading content.
