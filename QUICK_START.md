# Quick Start - Telegram Retry Feature

## 5-Minute Setup

### Step 1: Ensure `.env` File Exists
```bash
# In project root (blinkitHW/)
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHANNEL_ID=your_channel_here
```

### Step 2: Run the Watcher
```bash
python product_watcher.py
```

### Step 3: Provide Product Details
```
Enter product URL: https://blinkit.com/prn/x/prid/746548
Enter saved address label to select (default 'Home'): Home
Enter check interval in seconds (default 30): 30
Continue refreshing if product goes out of stock? (y/N): n
```

### Step 4: Wait for Product
- Script monitors automatically
- Checks every 30 seconds
- Shows in logs: `[WAITING] Product is still Coming Soon...`

### Step 5: Product Becomes Available!
- Product auto-detected ✅
- Added to cart ✅
- Verified in cart ✅
- **Telegram notification sent with buttons** 📲

### Step 6: Choose Your Action

**Option A: Via Telegram**
- Click **"Retry"** button in Telegram notification
- Watching restarts automatically

**Option B: Via Terminal**
- You'll see: `Would you like to retry watching this product? (y/N):`
- Type `y` and press Enter
- Same result - watching restarts

### Step 7: Monitor Restarts
- Each retry labeled: `RETRY #1`, `RETRY #2`, etc.
- Same product, location, settings
- Process continues indefinitely until purchase or manual stop

---

## What's New

| Feature | Before | After |
|---------|--------|-------|
| Retry | ❌ Manual re-run | ✅ One click/type |
| Telegram | Simple notifications | **Interactive buttons** |
| Parameters | Lost on restart | **Automatically preserved** |
| User Control | Terminal only | Terminal **+ Telegram** |
| Retry Count | Manual tracking | **Automatic logging** |

---

## The New Telegram Notification

When product is available:

```
🎉 Product Available!

Product: Hot Wheels Ferrari 250 GTO Toy Car & Hauler 
        Price - Buy Online at Best Price in India

📍Location: Home

Link:
Open on Blinkit

[🔄 Retry]              [❌ Cancel]
```

**Click Buttons:**
1. **🔄 Retry** → Restart watch with same settings
2. **❌ Cancel** → Stop watching (can restart manually later)

---

## Logs You'll See

### Initial Start
```
17th Feb 2026 06:15:00 PM - INFO - Product URL: https://blinkit.com/prn/x/prid/746548
17th Feb 2026 06:15:00 PM - INFO - Location: using site-saved address ('Home') via UI
17th Feb 2026 06:15:00 PM - INFO - Check interval: 30 seconds
17th Feb 2026 06:15:00 PM - INFO - Telegram notifications: ENABLED
```

### Monitoring
```
17th Feb 2026 06:15:23 PM - INFO - [CHECK #1] Navigating to product URL...
17th Feb 2026 06:15:23 PM - INFO - [WAITING] Product is still Coming Soon...
17th Feb 2026 06:15:53 PM - INFO - [CHECK #2] Navigating to product URL...
17th Feb 2026 06:15:53 PM - INFO - [WAITING] Product is still Coming Soon...
```

### Product Found
```
17th Feb 2026 06:16:00 PM - INFO - [AVAILABLE] Product is now AVAILABLE!
17th Feb 2026 06:16:01 PM - INFO - Step 1: Verifying product details...
17th Feb 2026 06:16:01 PM - INFO - [OK] Good match (similarity >= 0.90)
17th Feb 2026 06:16:02 PM - INFO - Step 2: Adding product to cart...
17th Feb 2026 06:16:04 PM - INFO - [OK] Clicked ADD selector
```

### Telegram Sent
```
17th Feb 2026 06:16:05 PM - INFO - [OK] Telegram notification with buttons sent successfully
17th Feb 2026 06:16:05 PM - INFO - [INFO] User can now click 'Retry' button...
```

### User Retries
```
[INFO] Watcher stopped.

Would you like to retry watching this product? (y/N): y

======================================================================
RETRY #1 - Starting new watch cycle with same parameters
======================================================================

[CHECK #1] Navigating to product URL...
```

---

## Telegram Not Showing Buttons?

**Check These:**
1. ✅ `.env` file has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID`
2. ✅ Bot is added to the channel/group
3. ✅ Token is correct (no spaces)
4. ✅ Channel ID is correct format (e.g., `-100123456789`)

**If Still Not Working:**
- Buttons are optional - terminal prompt works fine
- Type `y` when asked to retry instead
- Check logs for Telegram errors

---

## Multiple Products?

Run different instances in separate terminals:

**Terminal 1:**
```bash
python product_watcher.py
# Product 1
```

**Terminal 2:**
```bash
python product_watcher.py  
# Product 2
```

All send notifications to same Telegram channel ✅
Each retry independently ✅

---

## Advanced: Manual Retry from Code

```python
from product_watcher import ProductWatcher
import asyncio

async def main():
    # Store params
    params = {
        "product_url": "https://blinkit.com/prn/x/prid/746548",
        "latitude": None,
        "longitude": None,
        "check_interval": 30,
        "location_label": "Home",
        "continue_on_out_of_stock": False,
        "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN"),
        "telegram_channel_id": os.getenv("TELEGRAM_CHANNEL_ID")
    }
    
    # Retry 3 times
    for attempt in range(3):
        print(f"\nAttempt {attempt + 1}...")
        
        watcher = ProductWatcher(**params)
        success = await watcher.watch()
        
        if success:
            print("✓ Success!")
            break
        else:
            print("✗ Not available yet")
            if attempt < 2:
                print(f"Retrying in 5 seconds...")
                await asyncio.sleep(5)

asyncio.run(main())
```

---

## Keyboard Shortcuts

**During Monitoring:**
- `Ctrl+C` → Stop watcher immediately
- `Ctrl+C` twice quickly → Force terminate

**After Stop:**
- Type `y` → Retry with same settings
- Type `n` → Exit completely
- Just press Enter → Same as `n` (default)

---

## Status File Updates

After each action, `product_status.json` updated:

**When Monitoring:**
```json
{"status": "monitoring", "query_count": 5}
```

**When Available:**
```json
{"status": "available", "found_at": "2026-02-17T18:15:00"}
```

**When In Cart:**
```json
{"status": "added_to_cart", "product_name": "..."}
```

**When Purchased:**
```json
{"status": "purchased", "total_checks": 8}
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "ADD button not found" | Product might be disabled, try manual |
| "Wrong product in cart" | Check similarity ratio in logs |
| "Telegram not sending" | Verify `.env` file, check bot permissions |
| "Buttons not showing" | Try terminal retry (type `y`) instead |
| "Script crashes" | Check logs in `product_watcher.log` |
| "Can't detect product name" | Log level set to DEBUG for more details |

---

## Next Steps

1. **Get Telegram Bot:**
   - Chat with @BotFather on Telegram
   - `/newbot` → Create new bot
   - Copy token to `.env`

2. **Get Channel ID:**
   - Create a channel (or group)
   - Add bot to channel
   - Either:
     - Use @username as channel ID
     - Or send message to channel, get ID from webhook

3. **Test Notification:**
   - Run: `python product_watcher.py`
   - Wait for product or manually force success
   - Check Telegram for notification with buttons

4. **Enable Automatic Checkout (Optional):**
   - When asked "Automate checkout?", type `y`
   - Script completes purchase automatically

---

## Key Features Summary

✅ **Retry without terminal** - Click button, restart watching  
✅ **Preserve settings** - Same URL, location, interval  
✅ **Interactive buttons** - Retry or Cancel from Telegram  
✅ **Fallback prompt** - Terminal input works always  
✅ **Auto-tracking** - Retry count logged automatically  
✅ **Full backward compat** - Old code still works  
✅ **Production ready** - Fully tested and deployed  

---

## That's It! 🎉

You now have a fully automated product watcher with retry functionality. The best part? **No need to restart the script** - just click the Telegram button or type `y` in the terminal!

Enjoy your automated Blinkit shopping! 🛒
