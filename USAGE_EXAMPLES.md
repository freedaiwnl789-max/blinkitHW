# Usage Examples - Telegram Retry Feature

## Complete Workflow Example

### Step 1: Start the Watcher
```bash
python product_watcher.py
```

### Step 2: Provide Product Details
```
Enter product URL: https://blinkit.com/prn/x/prid/746548
Enter saved address label to select (default 'Home'): Home
Enter check interval in seconds (default 30): 30
Continue refreshing if product goes out of stock? (y/N): n
```

### Step 3: Monitoring Phase
- Script monitors the product every 30 seconds
- Logs each check:
  ```
  [CHECK #1] Navigating to product URL...
  [CHECK #2] Navigating to product URL...
  [WAITING] Product Hot Wheels Ferrari 250 GTO... is still Coming Soon...
  ```

### Step 4: Product Becomes Available
When the product is found:
```
[AVAILABLE] Product Hot Wheels Ferrari 250 GTO is now AVAILABLE!
Step 1: Verifying product details before adding to cart...
Step 2: Adding product to cart...
[OK] Clicked ADD selector: text=ADD
Step 3a: Verifying product in cart...
[CART] Product in cart: Hot Wheels Ferrari 250 GTO...
[OK] Cart product matches expected product (similarity=1.00)
Step 3b: Sending Telegram notification with action buttons...
[OK] Telegram notification with buttons sent successfully
✓ PRODUCT ADDED TO CART
Product: Hot Wheels Ferrari 250 GTO Toy Car & Hauler Price...
```

### Step 5: Automatic Checkout (Optional)
```
Automate checkout steps (Proceed to Pay, Select Payment, Pay Now)? (y/N): n
[USER] User chose not to automate checkout
Manually complete the checkout at your convenience.
```

### Step 6: Telegram Notification Received
You receive a notification in your Telegram channel with:
- Product name
- Location
- Link to product
- **Two buttons: "Retry" and "Cancel"**

### Step 7: Option A - Retry via Telegram Button
1. Click the **"Retry"** button in Telegram
2. Watcher restarts automatically:
   ```
   ======================================================================
   RETRY #1 - Starting new watch cycle with same parameters
   ======================================================================
   [CHECK #1] Navigating to product URL...
   [WAITING] Product is still Coming Soon...
   ```
3. Monitoring resumes with original settings

### Step 7: Option B - Retry via Terminal
1. You see the terminal prompt:
   ```
   [INFO] Watcher stopped.
   
   Would you like to retry watching this product? (y/N): 
   ```
2. Type `y` and press Enter
3. Same effect as Telegram button - restart happens

### Step 8: Subsequent Retries
- Each retry is numbered: Retry #1, #2, #3, etc.
- All parameters remain identical
- Process continues until purchase or manual stop (Ctrl+C)

## Retry Log Example
```
2026-02-17 06:15:23 - INFO - ======================================================================
2026-02-17 06:15:23 - INFO - RETRY #1 - Starting new watch cycle with same parameters
2026-02-17 06:15:23 - INFO - ======================================================================

2026-02-17 06:15:24 - INFO - [CHECK #1] Navigating to product URL...
2026-02-17 06:15:26 - INFO - [PRODUCT] Name: Hot Wheels Ferrari 250 GTO Toy Car & Hauler Price...
2026-02-17 06:15:26 - INFO - [WAITING] Product is still Coming Soon...
2026-02-17 06:15:57 - INFO - [CHECK #2] Navigating to product URL...
2026-02-17 06:15:59 - INFO - [PRODUCT] Name: Hot Wheels Ferrari 250 GTO Toy Car & Hauler Price...
2026-02-17 06:16:00 - INFO - [AVAILABLE] Product is now AVAILABLE!
```

## Status File Updates
After each action, `product_status.json` is updated:

**After Product Added to Cart:**
```json
{
  "status": "added_to_cart",
  "product_url": "https://blinkit.com/prn/x/prid/746548",
  "product_name": "Hot Wheels Ferrari 250 GTO Toy Car & Hauler Price - Buy Online at Best Price in India",
  "details": {
    "message": "Product successfully added to cart",
    "added_at": "2026-02-17T18:15:27.123456"
  }
}
```

**After Purchase:**
```json
{
  "status": "purchased",
  "details": {
    "completed_at": "2026-02-17T18:20:15.654321",
    "total_checks": 8
  }
}
```

## Manual Checkout Steps (if automate_checkout = y)
After product is in cart and Telegram notification sent:
```
Step 4: Clicking Proceed to pay button to go to checkout...
Step 5: Selecting Cash payment method...
Step 6: Clicking Pay Now button...
[SUCCESS] Checkout steps attempted/completed
```

## Environment Variables Required
```env
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=your_channel_id_here
```

## Tips for Multiple Product Monitoring
1. Run multiple watcher instances in different terminals (each with different products)
2. All send notifications to the same Telegram channel
3. Each can have different retry settings
4. Retry buttons work independently

## Troubleshooting

### Telegram Notification Not Sent?
- Check `.env` file has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID`
- Verify bot is added to the channel/group
- Check bot token and channel ID are correct
- See logs: `Telegram notification failed — check bot token, channel id...`

### Retry Button Not Working?
- Check if you're running in a supported terminal/environment
- Try using the terminal prompt instead (type 'y' when asked)
- Check Telegram bot webhook/polling is configured

### Product Detection Issues?
- Verify product URL is correct
- Check if location is properly selected
- Look for similarity ratio in logs (should be >= 0.70 for success)
- Check cart product name extraction in logs
