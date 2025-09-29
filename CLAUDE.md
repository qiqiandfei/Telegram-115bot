# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Telegram-115Bot is a Python-based Telegram bot for managing and controlling 115 Network Disk, supporting offline downloads, video uploads, directory synchronization, and more. The project integrates with:

- **115 Open Platform API** for cloud storage operations
- **Telegram Bot API** for user interaction
- **Telethon** for large file uploads (>20MB)
- **aria2** for download management
- **APScheduler** for automated tasks
- **Playwright** for web scraping

## Development Commands

### Docker Development
```bash
# Build and run locally
./build.sh                    # Build both base and application images
docker-compose up -d          # Run with docker-compose

# Manual build
docker build -f Dockerfile.base -t 115bot:base .
docker build -f Dockerfile -t 115bot:latest .
```

### Python Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run bot directly
python app/115bot.py

# Create Telegram session file
python create_tg_session_file.py
```

### Testing
- No formal test framework configured
- Manual testing via Telegram bot commands
- Check logs in `/config/115bot.log` (when running in container)

## Architecture Overview

### Core Components

1. **Entry Point** (`app/115bot.py`):
   - Main application bootstrap
   - Telegram bot initialization
   - Handler registration
   - Scheduler and message queue startup

2. **Initialization** (`app/init.py`):
   - Configuration loading from YAML
   - Global state management (logger, bot_config, openapi_115, etc.)
   - Module path setup for development/container environments

3. **Core Services** (`app/core/`):
   - `open_115.py`: 115 Network Disk API client (52K+ lines)
   - `scheduler.py`: APScheduler for automated tasks
   - `offline_task_retry.py`: Retry mechanism for failed downloads
   - `av_daily_update.py`: Daily AV content updates
   - `sehua_spider.py`: Web scraping functionality
   - `subscribe_movie.py`: Movie subscription system
   - `headless_browser.py`: Browser automation

4. **Handlers** (`app/handlers/`):
   - Telegram command and message handlers
   - Each handler focuses on specific functionality (auth, download, sync, etc.)
   - Registered in main application

5. **Utilities** (`app/utils/`):
   - `message_queue.py`: Async message processing
   - `logger.py`: Logging configuration
   - `aria2.py`: aria2 download client
   - `sqlitelib.py`: Database operations
   - `cover_capture.py`: Video thumbnail generation

### Key Design Patterns

- **Modular handlers**: Each Telegram command type has its own handler module
- **Async message queue**: Background processing for non-blocking operations
- **Global state**: Centralized configuration and clients in `init.py`
- **Plugin architecture**: Core services are independently loadable
- **Event-driven**: Scheduler triggers automated tasks (daily updates, retries)

### Configuration

- Main config: `config/config.yaml` (copy from `app/config.yaml.example`)
- Required configs: bot_token, allowed_user, 115 credentials
- Optional configs: Telegram API credentials for large file support
- Docker volumes: `/config`, `/tmp`, `/media`, `/CloudNAS`

### Authentication Flow

1. Bot token authentication with Telegram
2. 115 Network Disk OAuth via QR code (`/auth` command)
3. Optional Telegram user session for large file uploads
4. User authorization via `allowed_user` ID check

### Data Flow

1. User sends Telegram message/command
2. Handler processes request and validates permissions
3. Core services interact with external APIs (115, aria2, etc.)
4. Results queued for async delivery via message queue
5. Scheduler handles background tasks (subscriptions, retries)

## Common Operations

### Adding New Commands
1. Create handler function in appropriate `app/handlers/*_handler.py`
2. Register handler in `app/115bot.py` via `register_*_handlers()`
3. Add command to bot menu in `get_bot_menu()` if needed

### Configuration Changes
- Modify `app/config.yaml.example` for new config options
- Update config loading in `app/init.py`
- Use `/reload` command to refresh config without restart

### API Integration
- 115 API calls go through `app/core/open_115.py`
- External downloads use `app/utils/aria2.py`
- Web scraping uses `app/core/headless_browser.py`

## Important Notes

- The bot requires 115 Network Disk account and open platform access
- Large file uploads (>20MB) require Telegram API credentials
- Directory sync operations are destructive (delete existing files)
- All user interactions are restricted to `allowed_user` ID
- Async message queue handles background processing to prevent blocking