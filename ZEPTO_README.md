# Zepto Product Checker - Hot Wheels Tracker

An automated product monitoring and purchasing tool for Zepto, specifically designed to track and auto-purchase Hot Wheels products.

## Features

- ✅ **Multi-Product Tracking** - Monitor multiple Hot Wheels products from a list
- ✅ **Automated Location Selection** - Selects your saved delivery location via the UI modal
- ✅ **Availability Detection** - Detects when products come in stock
- ✅ **Auto-Purchase** - Automatically adds products to cart when available
- ✅ **Telegram Notifications** - Get instant alerts with product details
- ✅ **Fuzzy Matching** - Verifies product names to prevent wrong items
- ✅ **Status Tracking** - Logs all activity to `zepto_status.json`
- ✅ **Detailed Logging** - Color-coded logs with timestamps

## Setup

### 1. Requirements
- Python 3.8+
- Zepto account
- (Optional) Telegram bot for notifications

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the root directory:

```env
# Telegram Bot Configuration (Optional)
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHANNEL_ID=your_channel_id_here
```

## Authentication

The app uses cookie-based authentication for Zepto with intelligent login detection:

### Automatic Login Detection
The app automatically detects when you're logged in by checking for:
1. **UI Indicators** - Account menu, profile button, user address selector
2. **Local Storage** - Authentication tokens in browser storage
3. **Page Content** - Main page content that only appears when logged in
4. **Dynamic Detection** - Checks localStorage for user data

### Login Flow
- **First Run**: You'll need to manually log in to Zepto in the browser window
  - App checks for login automatically every 1 minute (up to 10 minutes)
  - If auto-detection fails but you're logged in, you can confirm manually
  - Waits 90+ seconds after login to ensure cookies are properly stored
  - Verifies login status before proceeding
  - Cookies are automatically saved to `zepto_cookies.json`

- **Subsequent Runs**: App automatically uses saved cookies
  - No manual login needed if cookies are still valid
  - If cookies expire, you'll be prompted to log in again
  - Same multi-step verification process applies

### 5. Add Products to Track

Edit `zepto/hot-wheels-urls.txt` and add products in this format:

```
Product Name - https://www.zepto.com/pn/product-name/pvid/xxx
Another Product - https://www.zepto.com/pn/another-product/pvid/yyy
```

Example:
```
Modern 100% Whole Wheat Bread - https://www.zepto.com/pn/modern-100-whole-wheat-bread-zero-maida-no-trans-fat/pvid/a9da2861-358c-4824-b58c-d357e36eeca7
```

## Usage

### On Windows
Double-click `start-zepto.bat` or run:
```bash
python zepto_checker.py
```

### On Linux/Mac
```bash
./start-zepto.sh
```

Or:
```bash
python3 zepto_checker.py
```

### Interactive Setup

1. **Select Product** - Choose from the list of products in `zepto/hot-wheels-urls.txt`
2. **Choose Location** - Enter the saved address label (e.g., 'home')
3. **Set Check Interval** - Enter seconds between checks (default: 30)
4. **Start Monitoring** - The app will start checking availability

## How It Works

1. **Authentication**
   - On first run: Opens browser and waits for you to log in
   - Automatically detects login completion
   - Saves cookies to `zepto_cookies.json` for future use
   - On subsequent runs: Automatically loads saved cookies and logs in
   - If cookies expire: Prompts for manual login again

2. **Initialization**
   - Loads all products from `zepto/hot-wheels-urls.txt`
   - Initializes browser with Zepto site
   - Authenticates using saved/new cookies
   - Selects your saved delivery location via the modal

3. **Monitoring Loop**
   - Navigates to product page
   - Extracts product name from DOM
   - Checks for "Add to Cart" button and out-of-stock status
   - Repeats at specified interval

4. **When Product Is Available**
   - Plays alert sound
   - Verifies product name with fuzzy matching
   - Clicks "Add to Cart" button
   - Opens cart
   - Sends Telegram notification (if configured)
   - Saves status to `zepto_status.json`

5. **Telegram Notification Format**
   ```
   ✅ Product Added to Cart
   
   📦 Product: [Product Name]
   🔗 URL: [Product URL]
   📍 Location: [Location Label]
   ⏰ Time: [Timestamp]
   ```

## Status Tracking

The app creates a `zepto_status.json` file with the current status:

```json
{
  "product_url": "https://www.zepto.com/...",
  "product_name": "Product Name",
  "location": "home",
  "status": "monitoring|available|out_of_stock|error",
  "timestamp": "2026-02-16T10:30:00.000000",
  "query_count": 5,
  "details": {},
  "action_needed": false
}
```

## Cookie Management

The app stores Zepto authentication cookies for seamless reuse:

- **File**: `zepto_cookies.json` (auto-created on first successful login)
- **Format**: JSON array of cookie objects
- **Persistence**: Cookies persist across sessions
- **Storage Wait**: After login detection, waits 90+ seconds (more than 1 minute) to ensure cookies are fully stored
- **Verification**: Verifies login after cookie storage before proceeding
- **Expiration**: If cookies expire, you'll be prompted to login again
- **Clearing**: Delete `zepto_cookies.json` to force a fresh login on next run
- **First Login Timeout**: 10 minutes to complete authentication

### Login Process Timeline
1. **Detection Phase** (first 10 minutes): 
   - Checks for login every 1 minute
   - Looks for UI indicators, auth tokens, page content
   
2. **Manual Confirmation** (if detection fails):
   - If login isn't detected after 10 minutes, asks you manually
   - "Have you successfully logged in to Zepto? (y/n)"
   - Allows you to confirm even if auto-detection doesn't work
   
3. **Storage Phase** (after confirmation - 90+ seconds):
   - Waits to ensure cookies are fully stored
   - Logs progress every 30 seconds
   
4. **Verification Phase**:
   - Double-checks login is still valid
   - Ensures cookies were saved properly
   
5. **Save Phase**:
   - Writes cookies to `zepto_cookies.json`
   - Proceeds with location selection

### Cookie Structure
Each cookie contains:
- `name` - Cookie name
- `value` - Cookie value
- `domain` - Cookie domain (.zepto.com)
- `path` - Cookie path
- `expires` - Expiration timestamp
- `secure` - HTTPS only flag
- `httpOnly` - HTTP only flag
- `sameSite` - SameSite policy

## Logging

All activity is logged to:
- **Console** - Color-coded, formatted output with ordinal dates
- **zepto_checker.log** - Detailed log file for debugging

## HTML Structure Reference

### Location Selector
- Container: `div.a0Ppr.__6VhjW`
- Button: `button[aria-label="home"]`
- Modal: `div[data-testid="address-model"]`

### Product Page
- Product Name: `div#product-features-wrapper h1`
- Add to Cart: `button[aria-label="Add to Cart"]` or `button:has-text("Add To Cart")`
- Cart Button: `button[data-testid="cart-btn"]`

## Troubleshooting

### Authentication Issues

#### "Have you successfully logged in to Zepto? (y/n)"
- This appears if auto-detection doesn't find login indicators after 10 minutes
- **Why it happens**: Zepto's UI elements might be in different locations or not loaded yet
- **Solution**: 
  - Answer "y" if you've manually logged in
  - The app will wait 90+ seconds and save your cookies
  - Next runs will use saved cookies automatically
  - Answer "n" if you haven't logged in yet, then log in and restart

#### "User appears to be logged out" repeated messages
- Auto-detection is checking but hasn't found login indicators yet
- App checks every 1 minute (waits until you log in or timeout)
- **Normal behavior**: Keep the page open and complete your login
- **What to do**:
  - Log in manually in the browser
  - App will detect it within the next 1 minute
  - Type "y" when manually prompted
  - The app will save cookies for next time

#### Auto-detection not working even though you're logged in
- **Why**: Different Zepto versions may have different UI structures or auth mechanisms
- **Improved Detection**: App now checks for:
  - Account/Profile buttons
  - User address selector
  - Auth tokens in localStorage
  - Main page content
- **Solution**:
  - Manually confirm when prompted: type "y"
  - Your cookies will be saved
  - Future runs will skip this step

#### "Saved cookies are invalid or expired"
- Zepto session expired or cookies were cleared
- Delete `zepto_cookies.json` to force re-login
- Run the app again and complete login (auto or manual)
- New cookies will be saved automatically

### Product Detection Issues

#### "No products found"
- Check that `zepto/hot-wheels-urls.txt` exists
- Verify file format: `Product Name - URL`

#### Location not selected
- Ensure your saved address label matches exactly (case-insensitive)
- Check that the modal opens properly by running with `headless=False`

#### Product not detected
- Verify product URL is correct
- Check if product page structure has changed
- Review browser logs for errors

### Telegram notifications not working
- Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHANNEL_ID` in `.env`
- Test bot token validity

### General Debugging

#### Check Log Files
- `zepto_checker.log` - Detailed execution logs
- `zepto_status.json` - Current status
- `zepto_cookies.json` - Saved authentication cookies

#### Force Fresh Login
```bash
# Delete the cookies file to force re-authentication
rm zepto_cookies.json
# or on Windows:
del zepto_cookies.json
```

#### Enable Headless Mode Off
The app runs with `headless=False` by default to show the browser. This is intentional for:
- Debugging authentication issues
- Monitoring product detection
- Verifying location selection

## Notes

- The app requires a visible browser window while monitoring and during login
- It will stop and cleanup when the product is purchased or user interrupts (Ctrl+C)
- Fuzzy matching requires >70% name similarity to proceed with auto-purchase
- All URLs and configurations are logged for reference
- **Manual Confirmation**: If auto-detection fails, you can confirm login manually ("y/n")
- Cookies are automatically saved and reused for subsequent runs
- First login: checks every 1 minute, up to 10 minutes timeout
- After login detected or confirmed: waits 90+ seconds for cookie storage
- If cookies expire, simply log in again - new cookies will be saved
- For best results, ensure stable internet and stay on page during login
- App intelligently detects login via:
  - UI indicators (buttons, menus)
  - Auth tokens in localStorage
  - Main page content visibility

## Contact & Support

For issues or improvements, refer to the log files:
- `zepto_checker.log` - Detailed execution logs
- `zepto_status.json` - Current status

---

**Version:** 1.0  
**Last Updated:** February 2026
