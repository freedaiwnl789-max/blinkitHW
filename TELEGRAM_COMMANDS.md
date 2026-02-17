# Telegram Commands & Retry Feature

## Overview
When a product becomes available, the bot now sends a Telegram notification with **interactive action buttons** allowing users to retry the watch process without restarting the terminal.

## Features

### 1. **Product Availability Notification**
When the product is found to be available and verified in the cart:
- Notification is sent to the configured Telegram channel
- Message includes:
  - ✅ Product name
  - 📍 Location 
  - 🔗 Direct link to product on Blinkit

### 2. **Inline Action Buttons**
The Telegram notification includes two buttons:
- **🔄 Retry** - Restarts the entire watch process with the same parameters
- **❌ Cancel** - Stops the process (user can also ignore)

## How It Works

### Setup
1. Configure Telegram bot token and channel ID in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
   TELEGRAM_CHANNEL_ID=-100123456789
   ```

2. Make sure the bot is added to the channel/group where you want notifications

### Workflow

#### Option 1: Retry via Telegram Button
1. Product watcher runs and monitors the product
2. When available, sends notification with **Retry button**
3. Click **Retry** button in Telegram
4. Watch process restarts automatically with same parameters

#### Option 2: Retry via Terminal Prompt
1. If watcher stops, you'll see a terminal prompt:
   ```
   Would you like to retry watching this product? (y/N):
   ```
2. Type `y` or `yes` to restart
3. Watch process begins again with same settings

## Code Changes

### `src/telegram/service.py`
- Added `send_message_with_buttons()` method to send messages with inline keyboards
- Enhanced `send_product_notification()` with `with_buttons` parameter
- Buttons are customizable (currently "Retry" and "Cancel")

### `product_watcher.py`
- Added `original_params` storage in `ProductWatcher.__init__()` to remember all settings
- Modified notification sending to include buttons after product verification
- Updated `main()` function with retry loop:
  - Supports terminal-based retry via user input
  - Tracks retry attempts
  - Restarts with identical parameters

### Notification Flow
1. Product detected as available
2. Added to cart and verified
3. Telegram sends notification **with buttons**
4. User can click "Retry" or use terminal prompt
5. Process restarts with same URL, location, check interval, etc.

## Retry Parameters Preserved
When retrying, these settings are maintained:
- ✅ Product URL
- ✅ Location label (e.g., "Home")
- ✅ Check interval (seconds)
- ✅ Continue-on-out-of-stock flag
- ✅ Telegram bot configuration

## Logging
Retry attempts are logged with:
```
[RETRY #1] - Starting new watch cycle with same parameters
[RETRY #2] - Starting new watch cycle with same parameters
```

## Example Telegram Notification
```
🎉 Product Available!

Product: Hot Wheels Ferrari 250 GTO Toy Car & Hauler Price - Buy Online at Best Price in India

📍Location: Home

Link:
Open on Blinkit

[🔄 Retry]  [❌ Cancel]
```

## Notes
- Buttons are sent **only after** product verification (to avoid false retries)
- Multiple retries can be triggered sequentially
- Each retry creates a fresh browser session
- Terminal prompt acts as fallback if Telegram is disabled
