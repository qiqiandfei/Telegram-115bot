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
# Install dependencies (traditional)
pip install -r requirements.txt

# Install dependencies (with uv - faster)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
uv pip install -r requirements.txt

# Run bot directly
python app/115bot.py

# Run with virtual environment and custom PYTHONPATH
source .venv/bin/activate && PYTHONPATH="/root/Telegram-115bot/app:/root/Telegram-115bot/app/utils:/root/Telegram-115bot/app/core:/root/Telegram-115bot/app/handlers:/root/Telegram-115bot" python app/115bot.py

# Create Telegram session file (required for >20MB file uploads)
python create_tg_session_file.py

# Test Python syntax
python3 -m py_compile app/handlers/download_handler.py
```

### Testing
- No formal test framework configured
- Manual testing via Telegram bot commands
- Check logs in `/config/115bot.log` (when running in container)
- Test utilities available:
  - `test_folder_extraction.py` - Test batch download folder name extraction logic

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
- Large file uploads (>20MB) require Telegram API credentials (`tg_api_id`, `tg_api_hash`, and `user_session.session`)
- Directory sync operations are destructive (delete existing files) - use with caution
- All user interactions are restricted to `allowed_user` ID (single ID or list)
- Async message queue handles background processing to prevent blocking
- Batch download state (`init.batch_downloads`, `init.pending_tasks`) stored in memory - lost on restart

## Batch Download Features

### Auto-Folder Creation
When users send multiple download links with text, the bot automatically:
1. Extracts first line + last line non-link text as folder name
2. Sanitizes characters (removes `:`, replaces `/\?*"<>|` with `-`)
3. Creates custom folder and downloads all files there
4. Files are saved directly (no `temp` subfolder for batch downloads)

**Example Input**:
```
miru(坂道みる/坂道美琉)原档合集
ed2k://|file|file1.mp4|...|/
ed2k://|file|file2.mp4|...|/
20251008
```

**Result**: Folder `miru(坂道みる-坂道美琉)原档合集20251008` created with files inside

### "移动到[]" (Move To) Command
After batch download completion (>1 links), users can reorganize files:
- Command format: `移动到[新文件夹名]`
- Creates subfolder and moves all downloaded files
- Works with or without auto-created folder names
- Example: `移动到[合集整理]`

### Key Implementation Details
- `extract_folder_name_from_text()` in `download_handler.py` - Extracts folder name
- `sanitize_folder_name()` - Cleans invalid characters
- `download_tasks_batch()` - Creates custom folder when `custom_folder_name` provided and `total_count > 1`
- Single downloads (1 link) still use `temp` folder wrapping for backward compatibility
- Batch downloads (≥2 links) save files directly without `temp` subfolder

## User Commands

### Basic Commands
- `/start` - Show help information
- `/auth` - 115 Network Disk OAuth authorization
- `/reload` - Reload configuration without restart
- `/q` - Cancel current conversation

### Download Commands
- Send `magnet:`, `ed2k://`, or `thunder://` links directly - Trigger batch download
- `/dl` - Add offline download (deprecated, pattern matching used instead)
- `/av [番号]` - Download AV content by code
- `/rl` - View/manage retry list for failed downloads

### Content Management
- `/sm [电影名称]` - Subscribe to movie updates
- `/sync` - Sync directory and create STRM soft links
- `/csh` - Manual crawl Sehua data
- `/cjav [yyyymmdd]` - Manual crawl javbee data
- Forward video to bot - Upload video to 115

### Special Message Handling
- `移动到[文件夹名]` - Batch move downloaded files to custom folder (after batch download)