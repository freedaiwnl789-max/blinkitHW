#!/usr/bin/env python3
"""
Zepto Product Checker
- Monitor Hot Wheels products from Zepto
- Auto-purchase when available
- Send Telegram notifications
"""

import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from fuzzywuzzy import fuzz

# Load environment variables from .env file
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Platform-specific sound alert
if sys.platform == "win32":
    import winsound

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.auth import BlinkitAuth
from src.telegram.service import TelegramBot

# Status file location
ZEPTO_STATUS_FILE = Path("zepto_status.json")
ZEPTO_URLS_FILE = Path("zepto/hot-wheels-urls.txt")

# ANSI color codes
PRODUCT_COLOR = '\033[95m'  # Magenta
RESET_COLOR = '\033[0m'

def colorize_product(name):
    """Wrap product name with color codes"""
    return f"{PRODUCT_COLOR}{name}{RESET_COLOR}"

def play_alert_sound():
    """Play an alert sound when product is available"""
    try:
        if sys.platform == "win32":
            winsound.Beep(1000, 500)
            time.sleep(0.2)
            winsound.Beep(1000, 500)
        else:
            print('\a', end='', flush=True)
    except Exception as e:
        logger.debug(f"Failed to play alert sound: {e}")


class OrdinalDateFormatter(logging.Formatter):
    """Custom formatter with ordinal dates and colored output"""
    
    LEVEL_COLORS = {
        'DEBUG': {'time': '\033[36m', 'level': '\033[36m', 'message': '\033[36m'},
        'INFO': {'time': '\033[94m', 'level': '\033[92m', 'message': '\033[92m'},
        'WARNING': {'time': '\033[94m', 'level': '\033[93m', 'message': '\033[93m'},
        'ERROR': {'time': '\033[94m', 'level': '\033[91m', 'message': '\033[91m'},
        'CRITICAL': {'time': '\033[94m', 'level': '\033[95m', 'message': '\033[95m'}
    }
    
    RESET = '\033[0m'
    
    def format(self, record):
        dt = datetime.fromtimestamp(record.created)
        day = dt.day
        month = dt.strftime('%b')
        year = dt.year
        time_str = dt.strftime('%I:%M:%S %p')
        
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        
        ordinal_date = f"{day}{suffix} {month} {year} {time_str}"
        colors = self.LEVEL_COLORS.get(record.levelname, self.LEVEL_COLORS['INFO'])
        
        colored_time = f"{colors['time']}{ordinal_date}{self.RESET}"
        colored_level = f"{colors['level']}{record.levelname}{self.RESET}"
        colored_message = f"{colors['message']}{record.getMessage()}{self.RESET}"
        
        log_message = f"{colored_time} - {colored_level} - {colored_message}"
        return log_message


# Configure logging
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(OrdinalDateFormatter())

file_handler = logging.FileHandler('zepto_checker.log', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d %b %Y %I:%M %p')
file_handler.setFormatter(file_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
    force=True
)
logger = logging.getLogger(__name__)


class ZeptoChecker:
    ZEPTO_COOKIES_FILE = Path("zepto_cookies.json")
    
    def __init__(self, product_url, product_name, location_label="home", check_interval=30, 
                 telegram_bot_token=None, telegram_channel_id=None):
        """
        Initialize the Zepto checker
        
        Args:
            product_url: Full Zepto product URL
            product_name: Expected product name
            location_label: Saved address label to select (default 'home')
            check_interval: Time between checks in seconds
            telegram_bot_token: Telegram bot token for notifications
            telegram_channel_id: Telegram channel ID for notifications
        """
        self.product_url = product_url
        self.product_name = product_name
        self.location_label = location_label or "home"
        self.check_interval = check_interval
        self.query_count = 0
        self.page = None
        self.browser = None
        self.context = None
        
        # Telegram bot configuration
        self.telegram_bot = None
        if telegram_bot_token and telegram_channel_id:
            self.telegram_bot = TelegramBot(telegram_bot_token, telegram_channel_id)

    async def save_cookies(self):
        """Save cookies from current context to file"""
        try:
            if self.context:
                cookies = await self.context.cookies()
                with open(self.ZEPTO_COOKIES_FILE, 'w') as f:
                    json.dump(cookies, f, indent=2)
                logger.info(f"[OK] Cookies saved to {self.ZEPTO_COOKIES_FILE}")
                return True
        except Exception as e:
            logger.debug(f"Error saving cookies: {e}")
        return False

    async def load_cookies(self):
        """Load cookies from file into context"""
        try:
            if not self.ZEPTO_COOKIES_FILE.exists():
                logger.info("No saved cookies found")
                return False
            
            with open(self.ZEPTO_COOKIES_FILE, 'r') as f:
                cookies = json.load(f)
            
            if self.context:
                await self.context.add_cookies(cookies)
                logger.info(f"[OK] Cookies loaded from {self.ZEPTO_COOKIES_FILE}")
                return True
        except Exception as e:
            logger.debug(f"Error loading cookies: {e}")
        return False

    async def is_logged_in(self):
        """Check if user is logged in by checking for logged-in indicators and URL changes"""
        try:
            # First check: Look for logged-in UI indicators
            # Check for signs of being logged in - look for account/profile elements
            # Common indicators: user menu, order history link, saved addresses, etc.
            logged_in_indicators = [
                "button[aria-label='Account']",
                "button[aria-label='Profile']",
                "[data-testid='user-menu']",
                "[data-testid='user-profile']",
                "a:has-text('My Orders')",
                "a:has-text('Addresses')",
                "a:has-text('My Account')",
                "button:has-text('Account')",
                "button:has-text('Profile')",
                "[class*='user-profile']",
                "[class*='user-menu']",
                "[class*='account']"
            ]
            
            for indicator in logged_in_indicators:
                try:
                    if await self.page.is_visible(indicator, timeout=2000):
                        logger.info("[OK] User is logged in - found UI indicator")
                        return True
                except Exception:
                    pass
            
            # Second check: Look for the location selector button which typically appears when logged in
            # The location selector has the user's saved address
            try:
                location_selector = "button:has(h3[data-testid='user-address'])"
                if await self.page.is_visible(location_selector, timeout=2000):
                    logger.info("[OK] User is logged in - found location selector")
                    return True
            except Exception:
                pass
            
            # Third check: Check if we can find any user-related cookies or local storage
            try:
                # Check for presence of user data in local storage
                user_data = await self.page.evaluate("""
                    () => {
                        // Check if user data is in localStorage
                        const userToken = localStorage.getItem('user') || localStorage.getItem('auth') || localStorage.getItem('token');
                        const userId = localStorage.getItem('userId') || localStorage.getItem('uid');
                        return (userToken || userId) ? true : false;
                    }
                """)
                if user_data:
                    logger.info("[OK] User is logged in - found auth token in storage")
                    return True
            except Exception as e:
                logger.debug(f"Could not check localStorage: {e}")
            
            # Fourth check: Look at current URL and check if it redirects (logged out users get redirected)
            try:
                current_url = self.page.url
                # If we're still on zepto.com and not on a login/redirect page, likely logged in
                if "zepto.com" in current_url and "login" not in current_url.lower() and "auth" not in current_url.lower():
                    # Check if page has main content (not a login/empty page)
                    has_content = await self.page.evaluate("""
                        () => {
                            // Check if page has actual content beyond login elements
                            const hasProducts = document.querySelector('[class*="product"]') !== null;
                            const hasCategories = document.querySelector('[class*="categor"]') !== null;
                            const hasMainContent = document.querySelectorAll('[class*="main"], [class*="content"], main').length > 0;
                            return hasProducts || hasCategories || hasMainContent;
                        }
                    """)
                    if has_content:
                        logger.info("[OK] User is logged in - found main content on page")
                        return True
            except Exception as e:
                logger.debug(f"Could not check page content: {e}")
            
            logger.info("[INFO] User appears to be logged out")
            return False
        except Exception as e:
            logger.debug(f"Error checking login status: {e}")
            return False

    async def login(self):
        """Manual login - user needs to authenticate"""
        try:
            logger.info("=" * 70)
            logger.info("ZEPTO LOGIN REQUIRED")
            logger.info("=" * 70)
            logger.info("Browser window is open - please log in to Zepto")
            logger.info("Steps:")
            logger.info("1. Click on your account/profile in the top right")
            logger.info("2. Enter your phone number or email")
            logger.info("3. Complete OTP verification or password authentication")
            logger.info("4. The app will detect when you're logged in")
            logger.info("-" * 70)
            
            # Navigate to home page
            await self.page.goto("https://www.zepto.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Wait for user to log in - check every 1 minute
            max_wait = 600  # 10 minutes timeout
            waited = 0
            check_interval = 60  # Check every 1 minute (60 seconds)
            
            while waited < max_wait:
                if await self.is_logged_in():
                    logger.info("[SUCCESS] Login detected!")
                    logger.info("Waiting for more than 1 minute to ensure cookies are properly stored...")
                    
                    # Wait for more than 1 minute (90 seconds) for cookies to be fully stored
                    wait_time = 90
                    for i in range(wait_time):
                        remaining = wait_time - i
                        if remaining % 30 == 0 or remaining <= 5:
                            logger.info(f"Storing cookies... ({remaining}s remaining)")
                        await asyncio.sleep(1)
                    
                    # Save cookies for future use
                    logger.info("Saving authentication cookies...")
                    if await self.save_cookies():
                        logger.info("[OK] Cookies saved successfully")
                    
                    # Verify login one more time before proceeding
                    logger.info("Verifying login status...")
                    if await self.is_logged_in():
                        logger.info("[OK] Login verified successfully - proceeding")
                        return True
                    else:
                        logger.warning("[WARNING] Login verification failed - retrying")
                        continue
                
                await asyncio.sleep(check_interval)
                waited += check_interval
                remaining_time = max_wait - waited
                logger.info(f"Waiting for login... ({waited}s elapsed, {remaining_time}s remaining)")
            
            # Timeout reached - ask user for manual confirmation
            logger.info("=" * 70)
            logger.info("LOGIN TIMEOUT - Waiting 10 minutes without detection")
            logger.info("=" * 70)
            logger.info("The app could not automatically detect your login.")
            logger.info("This might be because Zepto has a different login UI than expected.")
            logger.info("")
            logger.info("Please confirm manually:")
            
            # Give user option to confirm they're logged in
            manual_confirm = input("\nHave you successfully logged in to Zepto? (y/n): ").strip().lower()
            
            if manual_confirm in ('y', 'yes'):
                logger.info("[USER] Confirmed login - saving cookies...")
                logger.info("Waiting for more than 1 minute to ensure cookies are properly stored...")
                
                # Wait for more than 1 minute (90 seconds) for cookies to be fully stored
                wait_time = 90
                for i in range(wait_time):
                    remaining = wait_time - i
                    if remaining % 30 == 0 or remaining <= 5:
                        logger.info(f"Storing cookies... ({remaining}s remaining)")
                    await asyncio.sleep(1)
                
                # Save cookies
                if await self.save_cookies():
                    logger.info("[OK] Cookies saved successfully")
                    return True
                else:
                    logger.error("[FAILED] Could not save cookies")
                    return False
            else:
                logger.info("[CANCELLED] User cancelled login")
                return False
            
        except Exception as e:
            logger.error(f"Error during login: {e}")
            return False

    def write_status(self, status, details=None):
        """Write status to JSON file"""
        status_data = {
            "product_url": self.product_url,
            "product_name": self.product_name,
            "location": self.location_label,
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "query_count": self.query_count,
            "details": details or {},
            "action_needed": status == "available"
        }
        
        try:
            with open(ZEPTO_STATUS_FILE, 'w') as f:
                json.dump(status_data, f, indent=2)
            logger.info(f"Status: {status}")
            return True
        except Exception as e:
            logger.error(f"Error writing status file: {e}")
            return False

    async def select_location(self, page, location_label):
        """
        Select location from the modal
        
        Args:
            page: Playwright page object
            location_label: Location label to select (e.g., 'home')
        """
        try:
            logger.info(f"Selecting location: {location_label}...")
            
            # First approach: Try to find and click the location button by text content
            # This is more flexible than aria-label
            try:
                # Look for button that contains the location label text
                location_text_selector = f"button:has-text('{location_label}')"
                if await page.is_visible(location_text_selector, timeout=3000):
                    await page.click(location_text_selector, timeout=5000)
                    logger.info(f"[OK] Location button clicked via text selector")
                    await asyncio.sleep(1)
                    return True
            except Exception as e:
                logger.debug(f"Text selector approach failed: {e}")
            
            # Second approach: Click the user address button (more generic)
            try:
                address_button_selectors = [
                    "button:has(h3[data-testid='user-address'])",
                    "button[data-testid='user-address']",
                    "[data-testid='user-address']",
                    "h3[data-testid='user-address']"
                ]
                
                for selector in address_button_selectors:
                    try:
                        if await page.is_visible(selector, timeout=2000):
                            # If it's an h3, click the parent button
                            if "h3" in selector:
                                button = await page.query_selector(f"button:has({selector})")
                                if button:
                                    await button.click()
                                    logger.info(f"[OK] Location button clicked (parent of user-address)")
                                    break
                            else:
                                await page.click(selector, timeout=5000)
                                logger.info(f"[OK] Location button clicked (user-address)")
                                break
                    except Exception:
                        pass
                
                await asyncio.sleep(2)
            except Exception as e:
                logger.debug(f"Address button approach failed: {e}")
            
            # Third approach: Look for modal with any of the possible selectors
            logger.info("Looking for location modal...")
            
            modal_selectors = [
                "div[data-testid='address-model']",  # Original (typo in Zepto?)
                "div[data-testid='address-modal']",  # Correct spelling
                "[role='dialog']",
                "div[class*='modal']",
                "div[class*='Modal']"
            ]
            
            modal_found = False
            for modal_selector in modal_selectors:
                try:
                    if await page.is_visible(modal_selector, timeout=3000):
                        logger.info(f"[OK] Modal found with selector: {modal_selector}")
                        modal_found = True
                        break
                except Exception:
                    pass
            
            if not modal_found:
                logger.warning("Modal not found with standard selectors, trying alternative approach...")
                # Sometimes the modal might already be open from the click
                await asyncio.sleep(2)
            
            # Fourth approach: Look for the location option in the modal
            # Try by text content (most reliable)
            logger.info(f"Searching for '{location_label}' option in modal...")
            
            location_option_selectors = [
                f"button:has-text('{location_label.capitalize()}')",
                f"button:has-text('{location_label.upper()}')",
                f"text={location_label}",
                f"div:has-text('{location_label}')",
                f"span:has-text('{location_label}')"
            ]
            
            location_clicked = False
            for option_selector in location_option_selectors:
                try:
                    # Check if element is visible
                    elements = await page.query_selector_all(option_selector)
                    if elements:
                        logger.debug(f"Found {len(elements)} element(s) with selector: {option_selector}")
                        
                        # Click the first one that's visible
                        for element in elements:
                            try:
                                is_visible = await element.is_visible()
                                if is_visible:
                                    await element.click()
                                    logger.info(f"[OK] Location '{location_label}' selected")
                                    location_clicked = True
                                    break
                            except Exception:
                                pass
                        
                        if location_clicked:
                            break
                except Exception as e:
                    logger.debug(f"Option selector failed ({option_selector}): {e}")
            
            if location_clicked:
                await asyncio.sleep(2)
                logger.info("[OK] Location selected successfully")
                return True
            
            # If we get here, log what we found
            logger.warning("Could not find location option by text")
            logger.info("Attempting to find any clickable location options...")
            
            # Last resort: Click the first button we can find (might work if modal is open)
            try:
                buttons = await page.query_selector_all("button")
                for button in buttons:
                    text = await button.text_content()
                    if text and location_label.lower() in text.lower():
                        await button.click()
                        logger.info(f"[OK] Location found and clicked: {text}")
                        await asyncio.sleep(2)
                        return True
            except Exception as e:
                logger.debug(f"Last resort button search failed: {e}")
            
            logger.warning(f"[WARNING] Could not select location '{location_label}' - proceeding anyway")
            return True  # Return True to not block the flow - user might have selected manually
                    
        except Exception as e:
            logger.error(f"Error selecting location: {e}")
            return False

    async def get_product_name(self, page):
        """Extract product name from Zepto product page"""
        try:
            # Product name is in div id "product-features-wrapper" under h1 tag
            h1_selector = "#product-features-wrapper h1"
            
            try:
                product_name = await page.text_content(h1_selector, timeout=5000)
                if product_name:
                    return product_name.strip()
            except Exception as e:
                logger.debug(f"Failed to get product name from h1: {e}")
            
            # Fallback selectors
            selectors = [
                "h1",
                "[class*='product-title']",
                "[data-testid='product-name']"
            ]
            
            for selector in selectors:
                try:
                    product_name = await page.text_content(selector, timeout=3000)
                    if product_name and len(product_name.strip()) > 5:
                        return product_name.strip()
                except Exception:
                    pass
            
            return "Unknown"
        except Exception as e:
            logger.debug(f"get_product_name error: {e}")
            return "Unknown"

    async def check_product_availability(self):
        """Check if product is available on Zepto"""
        try:
            self.query_count += 1
            logger.info(f"[CHECK #{self.query_count}] Navigating to product URL...")
            
            # Navigate to product URL
            try:
                await self.page.goto(self.product_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"Navigation took longer: {e}")
            
            await asyncio.sleep(2)
            
            # Get product name
            product_name = await self.get_product_name(self.page)
            logger.info(f"[PRODUCT] {colorize_product(product_name)}")
            
            # Check for "Out of Stock" text
            is_out_of_stock = False
            try:
                out_of_stock_indicators = [
                    "text=Out of Stock",
                    "text=Out of stock",
                    "[class*='outofstock' i]",
                    "[class*='out-of-stock' i]"
                ]
                
                for indicator in out_of_stock_indicators:
                    try:
                        if await self.page.is_visible(indicator, timeout=2000):
                            is_out_of_stock = True
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Error checking out of stock: {e}")
            
            # Check for "Add to Cart" button
            add_to_cart_visible = False
            try:
                # Look for the Add to Cart button - aria-label or button text
                add_selectors = [
                    "button[aria-label='Add to Cart']",
                    "button:has-text('Add To Cart')",
                    "div[aria-label='Add to Cart'] button",
                    "button:has-text('Add to Cart')"
                ]
                
                for selector in add_selectors:
                    try:
                        if await self.page.is_visible(selector, timeout=2000):
                            add_to_cart_visible = True
                            break
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Error checking add to cart button: {e}")
            
            logger.info(f"[STATUS] Out of Stock: {is_out_of_stock}, Add to Cart visible: {add_to_cart_visible}")
            
            if add_to_cart_visible and not is_out_of_stock:
                # Product is AVAILABLE
                logger.info(f"[AVAILABLE] Product {colorize_product(product_name)} is now AVAILABLE!")
                play_alert_sound()
                
                self.write_status("available", {
                    "message": "Product is available for purchase!",
                    "product_name": product_name,
                    "found_at": datetime.now().isoformat()
                })
                return True
            else:
                # Product not available
                status_msg = "Out of Stock" if is_out_of_stock else "Not Available"
                logger.info(f"[WAITING] Product {colorize_product(product_name)} is {status_msg}...")
                self.write_status(status_msg.lower().replace(" ", "_"), {
                    "message": f"Product is {status_msg}",
                    "product_name": product_name,
                    "last_checked": datetime.now().isoformat()
                })
                return False
                
        except Exception as e:
            logger.error(f"Error checking product availability: {e}")
            self.write_status("error", {"error": str(e)})
            return False

    async def add_to_cart(self):
        """Add product to cart on Zepto"""
        try:
            logger.info("Step 1: Verifying product details...")
            product_name = await self.get_product_name(self.page)
            logger.info(f"[VERIFY] Product: {colorize_product(product_name)}")
            
            # Verify product name matches expected name (fuzzy matching)
            if self.product_name:
                similarity = fuzz.ratio(product_name.lower(), self.product_name.lower())
                if similarity < 70:
                    logger.warning(f"[WARNING] Product name mismatch! Expected: {self.product_name}, Found: {product_name}")
                else:
                    logger.info(f"[OK] Product name verified (match: {similarity}%)")
            
            logger.info("Step 2: Clicking Add to Cart button...")
            
            # Click the Add to Cart button
            add_selectors = [
                "button[aria-label='Add to Cart']",
                "button:has-text('Add To Cart')",
                "div[aria-label='Add to Cart'] button",
                "button:has-text('Add to Cart')"
            ]
            
            clicked = False
            for selector in add_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    clicked = True
                    logger.info("[OK] Add to Cart button clicked")
                    break
                except Exception:
                    pass
            
            if not clicked:
                logger.error("[FAILED] Could not click Add to Cart button")
                return False
            
            await asyncio.sleep(2)
            
            logger.info("Step 3: Opening cart...")
            
            # Click on the Cart button
            cart_selectors = [
                "button[aria-label='Cart']",
                "button[data-testid='cart-btn']",
                "div.group button[data-testid='cart-btn']"
            ]
            
            cart_clicked = False
            for selector in cart_selectors:
                try:
                    await self.page.click(selector, timeout=5000)
                    cart_clicked = True
                    logger.info("[OK] Cart button clicked")
                    break
                except Exception:
                    pass
            
            if not cart_clicked:
                logger.error("[FAILED] Could not click Cart button")
                return False
            
            await asyncio.sleep(2)
            
            # Send Telegram notification
            if self.telegram_bot:
                message = f"✅ *Product Added to Cart*\n\n"
                message += f"📦 Product: {product_name}\n"
                message += f"🔗 URL: {self.product_url}\n"
                message += f"📍 Location: {self.location_label}\n"
                message += f"⏰ Time: {datetime.now().strftime('%d %b %Y %I:%M %p')}"
                
                try:
                    await self.telegram_bot.send_message(message)
                    logger.info("[TELEGRAM] Notification sent")
                except Exception as e:
                    logger.error(f"Failed to send Telegram notification: {e}")
            
            logger.info("[SUCCESS] Product successfully added to cart!")
            print("\n" + "=" * 70)
            print("✓ PRODUCT ADDED TO CART")
            print("=" * 70)
            print(f"Product: {colorize_product(product_name)}")
            print(f"URL: {self.product_url}")
            print("=" * 70)
            
            self.write_status("added_to_cart", {
                "product_name": product_name,
                "added_at": datetime.now().isoformat()
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Error adding to cart: {e}")
            return False

    async def watch(self, max_checks=None):
        """
        Monitor product until available
        
        Args:
            max_checks: Max checks before giving up (None = infinite)
        """
        logger.info("=" * 70)
        logger.info("ZEPTO PRODUCT CHECKER - Hot Wheels Tracker")
        logger.info("=" * 70)
        logger.info(f"Product: {self.product_name}")
        logger.info(f"URL: {self.product_url}")
        logger.info(f"Location: {self.location_label}")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info(f"Max checks: {max_checks if max_checks else 'Unlimited'}")
        logger.info("-" * 70)
        
        # Initialize browser
        try:
            logger.info("Initializing browser...")
            auth = BlinkitAuth(headless=False)  # Show browser
            await auth.start_browser()
            self.page = auth.page
            self.browser = self.page.context.browser
            self.context = self.page.context
            
            # Navigate to Zepto home page first
            await self.page.goto("https://www.zepto.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Try to load saved cookies first
            logger.info("Checking for saved Zepto cookies...")
            if await self.load_cookies():
                # Reload page with cookies
                await self.page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(2)
                
                # Check if we're still logged in
                if not await self.is_logged_in():
                    logger.warning("[WARNING] Saved cookies are invalid or expired")
                    logger.info("Please log in again...")
                    if not await self.login():
                        logger.error("[FAILED] Could not complete login")
                        await auth.close_browser()
                        return False
            else:
                # No saved cookies - need to login
                logger.info("No saved cookies found - login required")
                if not await self.login():
                    logger.error("[FAILED] Could not complete login")
                    await auth.close_browser()
                    return False
            
            logger.info("[OK] Authentication successful")
            
            # Navigate back to home to select location
            await self.page.goto("https://www.zepto.com/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)
            
            # Select location
            if not await self.select_location(self.page, self.location_label):
                logger.error("[FAILED] Could not select location")
                await auth.close_browser()
                return False
            
            logger.info("[OK] Location selected successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize browser: {e}")
            return False
        
        # Initial status
        self.write_status("monitoring", {"started_at": datetime.now().isoformat()})
        
        check_num = 0
        start_time = datetime.now()
        
        try:
            while True:
                check_num += 1
                
                # Check availability
                is_available = await self.check_product_availability()
                
                if is_available:
                    # Product is available - auto add to cart
                    logger.info("[PURCHASING] Attempting to add to cart...")
                    success = await self.add_to_cart()
                    
                    if success:
                        logger.info("[SUCCESS] Product purchased successfully!")
                        break
                
                # Check max checks
                if max_checks and check_num >= max_checks:
                    logger.info(f"[LIMIT] Reached maximum checks ({max_checks})")
                    break
                
                # Wait before next check
                logger.info(f"Next check in {self.check_interval} seconds...")
                await asyncio.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("\n[STOPPED] Checker stopped by user")
            elapsed = datetime.now() - start_time
            self.write_status("stopped", {
                "reason": "User interrupted",
                "checks_performed": check_num,
                "duration": str(elapsed)
            })
            return False
        
        finally:
            try:
                # Close browser
                if self.browser:
                    await self.browser.close()
            except Exception:
                pass
        
        return True


def load_products_from_file():
    """Load product URLs from hot-wheels-urls.txt"""
    products = []
    try:
        if not ZEPTO_URLS_FILE.exists():
            logger.error(f"File not found: {ZEPTO_URLS_FILE}")
            return products
        
        with open(ZEPTO_URLS_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # Format: "Product Name - URL"
                parts = line.split(' - ', 1)
                if len(parts) == 2:
                    name, url = parts
                    products.append({
                        'name': name.strip(),
                        'url': url.strip()
                    })
        
        logger.info(f"Loaded {len(products)} products from {ZEPTO_URLS_FILE}")
        return products
    except Exception as e:
        logger.error(f"Error loading products: {e}")
        return products


async def main():
    """Main entry point"""
    
    print("\n" + "=" * 70)
    print("ZEPTO PRODUCT CHECKER - Hot Wheels Tracker")
    print("=" * 70)
    print("\nThis script will:")
    print("1. Monitor Hot Wheels products from Zepto")
    print("2. Auto-purchase when available")
    print("3. Send Telegram notifications")
    print("-" * 70)
    
    # Load products from file
    products = load_products_from_file()
    
    if not products:
        print("\nNo products found in zepto/hot-wheels-urls.txt")
        print("Please add product URLs in the format: Product Name - URL")
        return
    
    # Display available products
    print("\nAvailable products:")
    for i, product in enumerate(products, 1):
        print(f"{i}. {product['name']}")
    
    # Ask user to select a product
    try:
        choice = int(input("\nSelect product number to track (1-{}): ".format(len(products)))) - 1
        if choice < 0 or choice >= len(products):
            print("Invalid selection")
            return
    except ValueError:
        print("Invalid input")
        return
    
    selected_product = products[choice]
    
    # Ask for location
    location = input("\nEnter location label to select (default 'home'): ").strip().lower() or "home"
    
    # Ask for check interval
    try:
        check_interval = int(input("\nEnter check interval in seconds (default 30): ").strip() or "30")
    except ValueError:
        check_interval = 30
    
    # Load Telegram credentials
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_channel_id = os.getenv("TELEGRAM_CHANNEL_ID")
    
    logger.info(f"Product: {selected_product['name']}")
    logger.info(f"URL: {selected_product['url']}")
    logger.info(f"Location: {location}")
    logger.info(f"Check interval: {check_interval} seconds")
    if telegram_bot_token and telegram_channel_id:
        logger.info("Telegram notifications: ENABLED")
    else:
        logger.info("Telegram notifications: DISABLED")
    
    # Start checker
    checker = ZeptoChecker(
        selected_product['url'],
        selected_product['name'],
        location,
        check_interval,
        telegram_bot_token=telegram_bot_token,
        telegram_channel_id=telegram_channel_id
    )
    
    success = await checker.watch(max_checks=None)
    
    if success:
        logger.info("\n[SUCCESS] Product purchased successfully!")
    else:
        logger.info("\n[INFO] Checker stopped. Product not yet available.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
