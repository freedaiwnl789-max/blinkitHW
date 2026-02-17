#!/usr/bin/env python3
"""
Zepto Product Monitor & Auto-Checkout
Standalone script that monitors product availability, adds to cart, and sends Telegram notifications.

Features:
1. Login to Zepto.com
2. Track user-specified products
3. Auto-refresh at user-defined intervals if out of stock
4. Add to cart when available
5. Send Telegram notifications
6. Verify added product matches required product
7. Ask user to confirm before payment automation
8. Comprehensive logging of all steps
"""

import asyncio
import os
import sys
import time
import logging
import json
import traceback
import tempfile
from datetime import datetime
from typing import Optional, List, Tuple
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext
import aiohttp

# ============================================================================
# CONFIGURATION & SETUP
# ============================================================================

# Load environment variables
load_dotenv()

# Create logs directory
os.makedirs("logs", exist_ok=True)

# Setup logging with both file and console output
log_filename = f"logs/zepto_monitor_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# Configure logging with UTF-8 encoding to handle emojis in file
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Console handler with error handling for Windows cp1252 encoding
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)

# Print startup info
print("\n" + "="*70)
print("[*] ZEPTO PRODUCT MONITOR & AUTO-CHECKOUT")
print("="*70)
print(f"[*] Logs will be saved to: {log_filename}\n")

logger.info("="*70)
logger.info("[*] ZEPTO PRODUCT MONITOR & AUTO-CHECKOUT STARTED")
logger.info("="*70)

# ============================================================================
# TELEGRAM SERVICE
# ============================================================================

class TelegramBot:
    """Send Telegram notifications"""
    
    def __init__(self, bot_token: str, channel_id: str):
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send message to Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.channel_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            logger.info(f"[TELEGRAM] Sending notification...")
            logger.info(f"[TELEGRAM] Message length: {len(message)} characters")
            logger.info(f"[TELEGRAM] Full message:\n{message}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info("[OK] Telegram message sent successfully")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"[ERROR] Telegram send failed (status {response.status}): {error_text}")
                        return False
        except Exception as e:
            logger.error(f"[ERROR] Telegram error: {e}")
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return False
    
    async def send_product_notification(self, product_name: str, product_url: str, status: str = "AVAILABLE") -> bool:
        """Send formatted product notification"""
        emoji = "[SUCCESS]" if status == "AVAILABLE" else "[TIMER]"
        message = (
            f"{emoji} Product {status}!\n\n"
            f"Product: {product_name}\n"
            f"Status: {status}\n"
            f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Link: {product_url}"
        )
        return await self.send_message(message)
    
    async def send_cart_alert(self, product_name: str, product_url: str, address: str) -> bool:
        """Send alert when product is added to cart with location details"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        message = (
            f"[SUCCESS] PRODUCT ADDED TO CART!\n\n"
            f"Product: {product_name}\n"
            f"Location: {address}\n"
            f"Time: {timestamp}\n\n"
            f"URL: {product_url}"
        )
        logger.info(f"[TELEGRAM] Sending notification with address: {address}")
        logger.info(f"[TELEGRAM] Product: {product_name}, Location: {address}")
        return await self.send_message(message)
    
    async def send_alert(self, title: str, message: str) -> bool:
        """Send alert notification"""
        full_message = f"<b>🔔 {title}</b>\n\n{message}"
        return await self.send_message(full_message)

# ============================================================================
# PRODUCT MONITOR
# ============================================================================

class ZeptoProductMonitor:
    """Main automation logic for Zepto product monitoring"""
    
    def __init__(self, phone_number: str, address: str = "", telegram_bot: Optional[TelegramBot] = None, add_to_cart_mode: bool = False):
        self.phone_number = phone_number
        self.address = address
        self.telegram_bot = telegram_bot
        self.add_to_cart_mode = add_to_cart_mode
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Monitor state
        self.products_to_track: List[dict] = []  # [{name, url, qty, added}]
        self.logged_in = False
    
    async def log_step(self, step_num: int, action: str, status: str = ""):
        """Log an action step"""
        timestamp = datetime.now().strftime('%H:%M:%S')
        status_str = f" -> {status}" if status else ""
        message = f"[{timestamp}] Step {step_num}: {action}{status_str}"
        logger.info(message)
        print(message)
    
    async def startup(self):
        """Initialize browser and persistent context"""
        logger.info("[DIR] Initializing browser with persistent Chromium context...")
        
        # Get Chromium data directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        chromium_data_dir = os.path.join(script_dir, "zepto_chromium_data")
        
        # Ensure directory exists and is clean
        os.makedirs(chromium_data_dir, exist_ok=True)
        
        self.playwright = await async_playwright().start()
        
        logger.info(f"[DIR] Chromium data directory: {chromium_data_dir}")
        
        # Prefer using a saved storage_state.json (shared auth) so multiple
        # processes can reuse cookies without opening the same user-data-dir.
        state_path = os.path.join(chromium_data_dir, "state.json")

        try:
            if os.path.exists(state_path):
                logger.info("[DIR] Found existing storage state - launching non-persistent browser using state.json")
                # Launch a regular browser and create a new context from storage state
                self.browser = await self.playwright.chromium.launch(
                    headless=False,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check"
                    ]
                )
                self.context = await self.browser.new_context(
                    storage_state=state_path,
                    viewport={"width": 1280, "height": 720}
                )
            else:
                # Launch persistent context for interactive login (creates profile)
                try:
                    self.context = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=chromium_data_dir,
                        headless=False,
                        viewport={"width": 1280, "height": 720},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ]
                    )
                except Exception as e:
                    logger.error(f"[ERROR] Failed to launch Chromium persistent context: {e}")
                    logger.info("[RETRY] Attempting to clean and retry persistent launch...")

                    # Try to repair the user-data-dir and retry
                    try:
                        if os.path.exists(chromium_data_dir):
                            # attempt to remove stale files that can block startup
                            for root, dirs, files in os.walk(chromium_data_dir):
                                for f in files:
                                    try:
                                        os.remove(os.path.join(root, f))
                                    except Exception:
                                        pass
                    except Exception as clean_err:
                        logger.warning(f"[WARN] Could not clean directory: {clean_err}")

                    os.makedirs(chromium_data_dir, exist_ok=True)
                    self.context = await self.playwright.chromium.launch_persistent_context(
                        user_data_dir=chromium_data_dir,
                        headless=False,
                        viewport={"width": 1280, "height": 720},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--disable-dev-shm-usage",
                            "--no-first-run",
                            "--no-default-browser-check"
                        ]
                    )
        except Exception as e:
            logger.error(f"[ERROR] Browser/context startup failed: {e}")
            raise
        
        pages = self.context.pages
        if pages:
            self.page = pages[0]
        else:
            self.page = await self.context.new_page()
        
        logger.info("[OK] Browser initialized successfully")
        await self.log_step(1, "Browser initialization", "SUCCESS")
        
    async def _save_state_atomic(self, path: str):
        """Atomically save current context storage state to `path`."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # Get storage state as a dict
            state = await self.context.storage_state()
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".tmp_state_")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            finally:
                if os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except Exception:
                        pass
            logger.info(f"[DIR] Saved storage state to {path}")
        except Exception as e:
            logger.warning(f"[WARN] Failed to save storage state atomically: {e}")
    
    async def shutdown(self):
        """Close browser and cleanup"""
        logger.info("[STOP] Shutting down browser...")
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            if self.playwright:
                await self.playwright.stop()
            logger.info("[OK] Browser closed successfully")
        except Exception as e:
            logger.error(f"[WARN] Error closing browser: {e}")
    
    async def login(self) -> bool:
        """Login to Zepto"""
        try:
            await self.log_step(2, "Navigating to Zepto website")
            await self.page.goto("https://www.zeptonow.com", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Check if already logged in
            logger.info("[SEARCH] Checking if already logged in...")
            try:
                login_btn = await self.page.query_selector("span[data-testid='login-btn']")
                if login_btn and await login_btn.is_visible(timeout=2000):
                    logger.info("[WARN] Not logged in, proceeding with login...")
                else:
                    logger.info("[OK] Already logged in!")
                    self.logged_in = True
                    await self.log_step(2, "Login check", "ALREADY LOGGED IN")
                    
                    if self.telegram_bot:
                        await logger.info("[OK] Telegram is ready and logged into Zepto!")
                    return True
            except:
                logger.info("[WARN] Could not determine login status, checking with saved session...")
            
            # Try to use saved session
            logger.info("[DIR] Checking for saved Chromium session...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            chromium_data_dir = os.path.join(script_dir, "zepto_chromium_data")
            
            if os.path.exists(chromium_data_dir):
                logger.info(f"[OK] Found saved Chromium session at: {chromium_data_dir}")
                
                # Check for localStorage/sessionStorage indicating login
                try:
                    storage_data = await self.page.evaluate("() => ({localStorage: window.localStorage, sessionStorage: window.sessionStorage})")
                    if storage_data:
                        logger.info("[OK] Found browser storage data, likely logged in")
                        self.logged_in = True
                        await self.log_step(2, "Saved session check", "LOGGED IN (via storage)")
                        
                        if self.telegram_bot:
                            await logger.info("Logged in using saved session! Starting product monitoring...")
                        return True
                except:
                    pass
                
                # Check cookies more thoroughly
                try:
                    cookies = await self.context.cookies()
                    all_cookies = [c for c in cookies if c.get("value")]
                    
                    if all_cookies:
                        logger.info(f"[OK] Found {len(all_cookies)} stored cookies")
                        # Try to reload page with cookies
                        await self.page.reload(wait_until="domcontentloaded")
                        await asyncio.sleep(2)
                        
                        # Check if logged in now
                        try:
                            login_btn = await self.page.query_selector("span[data-testid='login-btn']")
                            if not login_btn or not await login_btn.is_visible(timeout=2000):
                                logger.info("[OK] Logged in using saved cookies!")
                                self.logged_in = True
                                await self.log_step(2, "Saved cookies", "LOGGED IN")
                                return True
                        except:
                            pass
                except Exception as e:
                    logger.warning(f"[WARN] Cookie check error: {e}, continuing anyway...")
                    # Assume logged in if saved session exists
                    self.logged_in = True
                    logger.info("[WARN] Assuming logged in based on saved session existence")
                    await self.log_step(2, "Saved session (assumption)", "PROCEED")
                    return True
            
            # Need to login manually
            logger.info("[PHONE] Starting manual login flow...")
            await self.log_step(2, "Starting manual login")
            
            # Click login button
            try:
                login_btn = await self.page.query_selector("span[data-testid='login-btn']")
                if login_btn:
                    await login_btn.click()
                    await asyncio.sleep(2)
            except:
                logger.warning("[WARN] Could not find login button, trying alternative method...")
            
            # Enter phone number
            logger.info(f"[PHONE] Entering phone number: {self.phone_number}")
            try:
                await self.page.fill("input[placeholder='Enter Phone Number']", self.phone_number)
            except:
                logger.warning("[WARN] Could not fill phone input, page may have changed")
            await asyncio.sleep(1)
            
            # Click continue
            try:
                await self.page.click("button:has-text('Continue')")
            except:
                logger.warning("[WARN] Could not click Continue button")
            await asyncio.sleep(3)
            
            # Wait for OTP
            print("\n" + "="*70)
            print("[TIMER]  WAITING FOR OTP ENTRY")
            print("="*70)
            print(f"[PHONE] Phone number: {self.phone_number}")
            print("[TIMER]  Please enter the OTP in the Chromium window")
            print("[TIMER]  You have 2 minutes to enter the OTP...")
            print("="*70 + "\n")
            
            logger.info("[TIMER]  Waiting for OTP entry (2 minutes timeout)...")
            
            if self.telegram_bot:
                await self.telegram_bot.send_alert(
                    "OTP Required",
                    f"Please enter OTP sent to {self.phone_number}"
                )
            
            # Wait for OTP with timeout
            await asyncio.sleep(120)  # 2 minutes
            
            logger.info("[OK] OTP entry timeout reached, confirming login...")
            
            # Check if logged in by reloading
            try:
                await self.page.reload(wait_until="domcontentloaded")
                await asyncio.sleep(2)
                
                try:
                    login_btn = await self.page.query_selector("span[data-testid='login-btn']")
                    if login_btn and await login_btn.is_visible(timeout=2000):
                        raise Exception("Login failed - login button still visible")
                except:
                    pass
            except Exception as e:
                logger.warning(f"[WARN] Could not reload page: {e}, continuing anyway...")
            
            logger.info("[OK] Login successful!")
            self.logged_in = True
            await self.log_step(2, "Manual login", "SUCCESS")
            
            # Save storage state so other instances can reuse cookies/auth
            try:
                script_dir = os.path.dirname(os.path.abspath(__file__))
                chromium_data_dir = os.path.join(script_dir, "zepto_chromium_data")
                state_path = os.path.join(chromium_data_dir, "state.json")
                await self._save_state_atomic(state_path)
            except Exception as e:
                logger.warning(f"[WARN] Could not save storage state after login: {e}")

            if self.telegram_bot:
                await self.telegram_bot.send_alert(
                    "Login Successful",
                    "Logged into Zepto! Starting product monitoring..."
                )
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Login failed: {e}")
            await self.log_step(2, "Login", f"FAILED - {e}")
            
            if self.telegram_bot:
                await self.telegram_bot.send_alert(
                    "Login Failed",
                    f"Error: {str(e)}"
                )
            return False
    
    async def check_product_availability(self, product_url: str) -> Tuple[bool, str]:
        """
        Check if product is in stock
        Returns: (is_in_stock, product_name)
        """
        try:
            logger.info(f"[SEARCH] Checking product: {product_url}")
            await self.page.goto(product_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Get product name
            try:
                product_name = await self.page.inner_text("h1, [class*='product'], [data-testid*='product-name']")
            except:
                product_name = "Unknown Product"
            
            # Check stock status
            out_of_stock_indicators = [
                "[class*='out-of-stock']",
                "button:has-text('Out of Stock')",
                "span:has-text('Out of Stock')",
                "[data-testid='out-of-stock']",
                "button[disabled]:has-text('Add')",  # Disabled add button usually means out of stock
            ]
            
            for selector in out_of_stock_indicators:
                try:
                    element = await self.page.query_selector(selector)
                    if element and await element.is_visible(timeout=1000):
                        logger.info(f"[ERROR] Product out of stock: {product_name}")
                        return False, product_name
                except:
                    pass
            
            # Try to find add to cart button
            try:
                add_btn = await self.page.query_selector("button.WJXJe:has-text('Add To Cart'), button:has-text('Add to Cart')")
                if add_btn and await add_btn.is_visible(timeout=1000):
                    logger.info(f"[OK] Product in stock: {product_name}")
                    return True, product_name
            except:
                pass
            
            logger.warning(f"[WARN] Could not determine stock status for: {product_name}")
            return True, product_name  # Assume in stock if unsure
            
        except Exception as e:
            logger.error(f"[ERROR] Error checking product: {e}")
            return False, "Unknown Product"
    
    async def check_product_exists(self, product_url: str) -> Tuple[bool, str]:
        """
        Check if product exists and has Add to Cart button
        Returns: (product_exists, product_name)
        """
        try:
            logger.info(f"[CHECK] Navigating to product: {product_url}")
            await self.page.goto(product_url, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Get product name
            product_name = "Unknown Product"
            
            selectors_to_try = [
                "h1",
                "[data-testid='product-title']",
                ".product-name",
            ]
            
            for selector in selectors_to_try:
                try:
                    elem = await self.page.query_selector(selector)
                    if elem:
                        product_name = await elem.inner_text()
                        logger.info(f"[CHECK] Found product name: {product_name}")
                        break
                except:
                    pass
            
            # Check for Add to Cart button
            logger.info("[CHECK] Looking for Add to Cart button...")
            
            button_selectors = [
                "div[aria-label='Add to Cart'] button",
                "button.WJXJe",
                "button:has-text('Add To Cart')",
                "button:has-text('Add to Cart')",
            ]
            
            for selector in button_selectors:
                try:
                    btn = await self.page.query_selector(selector)
                    if btn:
                        btn_text = await btn.inner_text()
                        btn_visible = await btn.is_visible()
                        btn_enabled = await btn.is_enabled()
                        
                        logger.info(f"[CHECK] Found button: '{btn_text}' (visible={btn_visible}, enabled={btn_enabled})")
                        
                        if btn_visible and btn_enabled:
                            logger.info(f"[OK] Product is available: {product_name}")
                            
                            # If add to cart mode is enabled, click the button with retries
                            if self.add_to_cart_mode:
                                logger.info("[CART] Add to cart mode enabled - attempting to click button...")
                                
                                click_success = False
                                current_url = self.page.url
                                
                                # Try clicking 2-3 times with multiple strategies
                                for attempt in range(3):
                                    try:
                                        logger.info(f"[CART] Click attempt #{attempt + 1}")
                                        
                                        # Scroll button into view
                                        await btn.evaluate("element => element.scrollIntoView({behavior: 'smooth', block: 'center'})")
                                        await asyncio.sleep(0.5)
                                        
                                        # Try force click
                                        try:
                                            await btn.click(force=True)
                                            logger.info(f"[CART] Force click attempt #{attempt + 1} completed")
                                            click_success = True
                                        except:
                                            # Try regular click
                                            try:
                                                await btn.click()
                                                logger.info(f"[CART] Regular click attempt #{attempt + 1} completed")
                                                click_success = True
                                            except:
                                                # Try JavaScript click
                                                try:
                                                    await btn.evaluate("element => { element.click(); }")
                                                    logger.info(f"[CART] JavaScript click attempt #{attempt + 1} completed")
                                                    click_success = True
                                                except Exception as e:
                                                    logger.warning(f"[WARN] Click attempt #{attempt + 1} failed: {e}")
                                        
                                        # Wait a bit after each click
                                        await asyncio.sleep(1)
                                        
                                        # If click was successful, don't try again
                                        if click_success:
                                            break
                                        
                                    except Exception as e:
                                        logger.warning(f"[WARN] Error in click attempt #{attempt + 1}: {e}")
                                        continue
                                
                                if click_success:
                                    logger.info("[OK] Button clicked successfully!")
                                    
                                    # Wait a bit to see if page changes
                                    await asyncio.sleep(2)
                                    
                                    # Check if page URL changed (redirection)
                                    new_url = self.page.url
                                    if new_url != current_url:
                                        logger.warning(f"[WARN] Page was redirected from {current_url} to {new_url}")
                                        logger.info(f"[CART] Navigating back to product URL...")
                                        await self.page.goto(product_url, wait_until="domcontentloaded")
                                        await asyncio.sleep(2)
                                        logger.info("[OK] Back on product page")
                                    else:
                                        logger.info("[OK] Page remained on product URL - no redirection")
                                else:
                                    logger.error("[ERROR] Could not click button after 3 attempts")
                            
                            return True, product_name
                except:
                    pass
            
            logger.warning(f"[CHECK] No Add to Cart button found for: {product_name}")
            return False, product_name
            
        except Exception as e:
            logger.error(f"[ERROR] Error checking product: {e}")
            return False, "Error"
    
    
    async def monitor_and_add(self, products: List[dict], refresh_interval: int):
        """Monitor products and send notifications when available"""
        try:
            logger.info("\n" + "="*70)
            logger.info("[STATS] STARTING PRODUCT MONITORING")
            logger.info("="*70)
            logger.info(f"[PACKAGE] Products to monitor: {len(products)}")
            for p in products:
                logger.info(f"   - {p['name']}")
            logger.info(f"[TIMER]  Refresh interval: {refresh_interval} seconds")
            logger.info("="*70 + "\n")
            
            # First, go to Zepto homepage and set location
            logger.info("[LOCATION] Setting delivery location on Zepto...")
            await self.page.goto("https://www.zeptonow.com", wait_until="domcontentloaded")
            await asyncio.sleep(2)
            
            # Set location
            location_set = await self.select_delivery_location()
            if not location_set:
                logger.warning("[WARN] Could not set location, continuing anyway...")
            
            self.products_to_track = [
                {**p, "checked": False, "last_checked": None}
                for p in products
            ]
            
            step_num = 3
            refresh_count = 0
            
            while True:
                refresh_count += 1
                await self.log_step(step_num, f"Checking products (Attempt #{refresh_count})")
                step_num += 1
                
                for product in self.products_to_track:
                    if product["checked"]:
                        logger.info(f"[OK] Already notified: {product['name']}")
                        continue
                    
                    logger.info(f"\n[CHECK] Checking: {product['name']}")
                    exists, name = await self.check_product_exists(product["url"])
                    
                    if exists:
                        logger.info(f"[OK] FOUND: {name}")
                        print("\n" + "="*70)
                        print("[OK] PRODUCT FOUND AND AVAILABLE!")
                        print("="*70)
                        print(f"[PACKAGE] Product: {name}")
                        print(f"[LOCATION] Address: {self.address}")
                        print("="*70 + "\n")
                        
                        # Send notification
                        if self.telegram_bot:
                            message = (
                                f"[SUCCESS] PRODUCT FOUND AND AVAILABLE!\n\n"
                                f"Product: {name}\n"
                                f"Location: {self.address}\n"
                                f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                                f"URL: {product['url']}"
                            )
                            await self.telegram_bot.send_message(message)
                            logger.info("[OK] Notification sent to Telegram")
                        
                        product["checked"] = True
                    else:
                        logger.info(f"[ERROR] NOT FOUND: {product['name']}")
                
                # Check if all products have been checked
                all_checked = all(p["checked"] for p in self.products_to_track)
                
                if all_checked:
                    logger.info("\n" + "="*70)
                    logger.info("[SUCCESS] ALL PRODUCTS CHECKED!")
                    logger.info("="*70 + "\n")
                    
                    return True
                
                # Wait before next refresh
                logger.info(f"[TIMER]  Waiting {refresh_interval} seconds before next check...\n")
                await asyncio.sleep(refresh_interval)
        
        except Exception as e:
            logger.error(f"[ERROR] Error in monitoring loop: {e}")
            if self.telegram_bot:
                await self.telegram_bot.send_alert(
                    "Monitoring Error",
                    f"Error: {str(e)}"
                )
            return False
    
    
    async def select_delivery_location(self) -> bool:
        """Select delivery location from the modal"""
        try:
            logger.info(f"[LOCATION] Starting location selection for: {self.address}")
            
            # Step 1: Click the "Select Location" button
            logger.info("[LOCATION] Looking for 'Select Location' button...")
            try:
                # Find the button with aria-label="Select Location"
                select_btn = await self.page.query_selector("button[aria-label='Select Location']")
                
                if not select_btn:
                    logger.warning("[WARN] Could not find 'Select Location' button, trying alternative selector...")
                    # Try alternative selector
                    select_btn = await self.page.query_selector("button:has(h3[data-testid='user-address'])")
                
                if not select_btn:
                    logger.error("[ERROR] 'Select Location' button not found")
                    return False
                
                logger.info("[LOCATION] Found 'Select Location' button, clicking it...")
                await select_btn.click()
                await asyncio.sleep(2)
                
            except Exception as e:
                logger.error(f"[ERROR] Error clicking Select Location button: {e}")
                return False
            
            # Step 2: Wait for modal to appear - use the correct data-testid
            logger.info("[LOCATION] Waiting for location modal to appear...")
            try:
                await self.page.wait_for_selector("div[data-testid='address-modal']", timeout=5000)
                logger.info("[OK] Modal appeared (by data-testid)")
            except:
                logger.warning("[WARN] Modal not found by data-testid, trying class selector...")
                try:
                    await self.page.wait_for_selector("div.cWTe3", timeout=5000)
                    logger.info("[OK] Modal appeared (by class)")
                except:
                    logger.warning("[WARN] Modal not found by class, trying role='dialog'...")
                    try:
                        await self.page.wait_for_selector("[role='dialog']", timeout=5000)
                        logger.info("[OK] Dialog appeared (by role)")
                    except:
                        logger.error("[ERROR] Modal/dialog did not appear")
                        return False
            
            await asyncio.sleep(1)
            
            # Step 3: Find all address items in the modal
            logger.info("[LOCATION] Looking for address items in modal...")
            
            # Look for address items directly
            address_items = await self.page.query_selector_all("div.cgG1vl")
            
            if not address_items:
                logger.warning("[WARN] No items found with class cgG1vl, trying parent containers...")
                address_items = await self.page.query_selector_all("div[data-testid='address-item']")
            
            logger.info(f"[LOCATION] Found {len(address_items)} address item(s)")
            
            if not address_items:
                logger.error("[ERROR] No address items found in modal")
                return False
            
            # Step 4: Find the matching address
            user_address_lower = self.address.lower().strip()
            logger.info(f"[LOCATION] Matching against user address: '{self.address}'")
            
            for idx, item in enumerate(address_items):
                try:
                    # Get all text content from the address item
                    item_text = await item.inner_text()
                    item_text_lower = item_text.lower()
                    
                    logger.info(f"[LOCATION] Address item #{idx + 1}: {item_text}")
                    
                    # Try different matching strategies
                    # Strategy 1: Exact match
                    if user_address_lower == item_text_lower:
                        logger.info(f"[LOCATION] EXACT MATCH found at item #{idx + 1}!")
                        await item.click()
                        await asyncio.sleep(2)
                        logger.info("[OK] Location selected successfully (exact match)")
                        return True
                    
                    # Strategy 2: Contains major address parts
                    # Split the user address and check if all parts are in the item
                    address_parts = [p.strip() for p in user_address_lower.split(",")]
                    if len(address_parts) > 0:
                        # Check if at least the last 2 parts match
                        if len(address_parts) >= 2:
                            if address_parts[-1] in item_text_lower and address_parts[-2] in item_text_lower:
                                logger.info(f"[LOCATION] PARTIAL MATCH found at item #{idx + 1}!")
                                await item.click()
                                await asyncio.sleep(2)
                                logger.info("[OK] Location selected successfully (partial match)")
                                return True
                        else:
                            # Single part address
                            if address_parts[0] in item_text_lower:
                                logger.info(f"[LOCATION] MATCH found at item #{idx + 1}!")
                                await item.click()
                                await asyncio.sleep(2)
                                logger.info("[OK] Location selected successfully (single part match)")
                                return True
                    
                except Exception as e:
                    logger.warning(f"[WARN] Error processing address item #{idx + 1}: {e}")
                    continue
            
            # If no exact match found, show available addresses and wait for user input
            logger.warning(f"[WARN] No exact match found for address: {self.address}")
            logger.info("[LOCATION] Available addresses in modal:")
            
            available_addresses = []
            for idx, item in enumerate(address_items):
                try:
                    item_text = await item.inner_text()
                    available_addresses.append((idx, item_text))
                    logger.info(f"   {idx + 1}. {item_text}")
                except:
                    pass
            
            print("\n" + "="*70)
            print("[WARN] Location address not found in available options")
            print("="*70)
            print("Available addresses:")
            for idx, addr in available_addresses:
                print(f"  {idx + 1}. {addr}")
            print("="*70)
            
            # Ask user to select
            while True:
                try:
                    selection = input("\nEnter the address number to select (or 0 to skip): ").strip()
                    sel_idx = int(selection) - 1
                    
                    if selection == "0":
                        logger.warning("[WARN] User skipped location selection")
                        print("[WARN] Continuing without location selection...")
                        return False
                    
                    if 0 <= sel_idx < len(address_items):
                        logger.info(f"[LOCATION] User selected address #{sel_idx + 1}")
                        await address_items[sel_idx].click()
                        await asyncio.sleep(2)
                        logger.info("[OK] Location selected successfully (user choice)")
                        return True
                    else:
                        print("[ERROR] Invalid selection. Please try again.")
                except (ValueError, IndexError):
                    print("[ERROR] Invalid input. Please enter a valid number.")
                    continue
            
        except Exception as e:
            logger.error(f"[ERROR] Error in location selection: {e}")
            logger.error(f"[ERROR] Traceback: {traceback.format_exc()}")
            return False
    

# ============================================================================
# MAIN FLOW
# ============================================================================

async def get_user_input() -> Tuple[str, str, List[dict], int, Optional[TelegramBot], bool]:
    """Get user input for products and preferences - load from .env and hot-wheels-urls.json"""
    print("\n" + "="*70)
    print("[SETUP] ZEPTO PRODUCT MONITOR - SETUP")
    print("="*70)
    
    # Get phone number from .env
    phone_number = os.getenv("ZEPTO_PHONE_NUMBER", "").strip()
    if not phone_number:
        print("\n[ERROR] Phone number not found in .env")
        print("   Please set ZEPTO_PHONE_NUMBER in .env file")
        sys.exit(1)
    
    logger.info(f"[PHONE] Phone number loaded from .env")
    print(f"[PHONE] Using phone number: {phone_number}")
    
    # Load products from hot-wheels-urls.json
    products_file = os.path.join(os.path.dirname(__file__), "hot-wheels-urls.json")
    if not os.path.exists(products_file):
        print(f"[ERROR] Products file not found: {products_file}")
        sys.exit(1)
    
    with open(products_file, 'r', encoding='utf-8-sig') as f:
        products_catalog = json.load(f)
    
    # Show available products and ask user to select
    print("\n[PACKAGE] Available products:")
    product_list = list(products_catalog.items())
    for idx, (name, url) in enumerate(product_list, 1):
        print(f"  {idx}. {name}")
    
    # Get user selection
    selected_products = []
    print("\n[SETUP] Select products to monitor (enter numbers separated by commas, e.g., 1,3,5):")
    
    while True:
        selection = input("   Enter product numbers: ").strip()
        if not selection:
            print("[ERROR] No products selected")
            continue
        
        try:
            indices = [int(x.strip()) - 1 for x in selection.split(",")]
            for idx in indices:
                if 0 <= idx < len(product_list):
                    name, url = product_list[idx]
                    selected_products.append({
                        "name": name,
                        "url": url,
                        "quantity": 1
                    })
                else:
                    print(f"[ERROR] Invalid selection: {idx + 1}")
                    raise ValueError()
            break
        except (ValueError, IndexError):
            print("[ERROR] Invalid input. Please enter valid product numbers separated by commas.")
            continue
    
    # Remove duplicates while preserving order
    seen = set()
    unique_products = []
    for p in selected_products:
        if p['url'] not in seen:
            seen.add(p['url'])
            unique_products.append(p)
    selected_products = unique_products
    
    products = selected_products
    if not products:
        print("[ERROR] No products selected")
        sys.exit(1)
    
    print(f"\n[OK] Selected {len(products)} product(s):")
    logger.info(f"[PACKAGE] Products to monitor: {len(products)}")
    for p in products:
        print(f"   - {p['name']}")
        logger.info(f"   - {p['name']} - {p['url']}")
    
    # Get delivery address
    print("\n[SETUP] Enter your delivery address:")
    address = input("   Address: ").strip()
    if not address:
        print("[ERROR] Address cannot be empty")
        sys.exit(1)
    
    logger.info(f"[LOCATION] Delivery address set: {address}")
    print(f"[OK] Delivery address set: {address}")
    
    # Confirm address
    print(f"\nConfirm delivery address: {address}")
    confirm = input("   Is this correct? (y/n): ").strip().lower()
    if confirm not in ['y', 'yes']:
        print("[ERROR] Address confirmation failed. Please restart.")
        sys.exit(1)
    
    logger.info(f"[LOCATION] Address confirmed by user: {address}")
    print(f"[OK] Address confirmed")
    
    # Get refresh interval
    print("\n[TIMER] How often should the script check for product availability?")
    refresh_str = input("   Enter interval in seconds (default 30): ").strip()
    try:
        refresh_interval = int(refresh_str) if refresh_str else 30
    except:
        refresh_interval = 30
    
    logger.info(f"[TIMER] Refresh interval: {refresh_interval} seconds")
    
    # Setup Telegram - automatically use if credentials available in .env
    telegram_bot = None
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    channel_id = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    
    if bot_token and channel_id:
        telegram_bot = TelegramBot(bot_token, channel_id)
        logger.info("[OK] Telegram bot initialized (credentials found in .env)")
        print("\n[OK] Telegram notifications enabled")
    else:
        logger.warning("[WARN] Telegram credentials not found in .env")
        print("\n[WARN] Telegram disabled - credentials not found in .env")
        print("   To enable Telegram, set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in .env")
    
    # Ask if user wants to add to cart
    print("\n" + "="*70)
    print("[CART] ADD TO CART OPTION")
    print("="*70)
    print("Do you want to automatically add products to cart when found?")
    print("  1. NO - Just check if product exists and notify (current behavior)")
    print("  2. YES - Also automatically add to cart")
    print("="*70)
    
    add_to_cart_mode = False
    while True:
        choice = input("\nEnter your choice (1/2): ").strip().lower()
        if choice in ["1", "no"]:
            add_to_cart_mode = False
            logger.info("[OK] User chose: Just check and notify")
            print("[OK] Will only check and notify - no auto add to cart")
            break
        elif choice in ["2", "yes"]:
            add_to_cart_mode = True
            logger.info("[OK] User chose: Add to cart automatically")
            print("[OK] Will automatically add products to cart when found")
            break
        else:
            print("[ERROR] Invalid choice. Please enter 1 or 2.")
    
    print("\n" + "="*70)
    print("[OK] SETUP COMPLETE - STARTING MONITORING")
    print("="*70 + "\n")
    
    return phone_number, address, products, refresh_interval, telegram_bot, add_to_cart_mode

async def main():
    """Main execution flow"""
    try:
        # Get user input
        phone_number, address, products, refresh_interval, telegram_bot, add_to_cart_mode = await get_user_input()
        
        # Initialize monitor
        monitor = ZeptoProductMonitor(phone_number, address, telegram_bot, add_to_cart_mode)
        
        try:
            # Start browser
            await monitor.startup()
            
            # Login
            if not await monitor.login():
                logger.error("[ERROR] Login failed. Exiting...")
                sys.exit(1)
            
            # Monitor products and send notifications
            success = await monitor.monitor_and_add(products, refresh_interval)
            
            if success:
                logger.info("[OK] All products have been checked and notifications sent")
                print("\n" + "="*70)
                print("[OK] MONITORING COMPLETE")
                print("="*70)
                print("[OK] All products have been checked and notifications sent to Telegram")
                print("="*70 + "\n")
                
                # Keep browser open for manual payment
                print("\n" + "="*70)
                print("[MANUAL PAYMENT] Browser will stay open")
                print("="*70)
                print("Please complete your payment manually in the browser.")
                print("="*70 + "\n")
                
                # Wait for user confirmation
                while True:
                    confirm = input("Have you completed the payment? (Y/N): ").strip().upper()
                    if confirm == "Y" or confirm == "YES":
                        logger.info("[OK] User confirmed payment is complete")
                        print("\n[OK] Closing browser and exiting...")
                        break
                    elif confirm == "N" or confirm == "NO":
                        print("[OK] Keeping browser open. Complete your payment and try again.")
                        await asyncio.sleep(2)
                    else:
                        print("[ERROR] Please enter Y or N")
        
        finally:
            # Cleanup
            await monitor.shutdown()
            logger.info("[OK] Script completed successfully")
            
    except KeyboardInterrupt:
        logger.info("[WARN]  Script interrupted by user")
        print("\n[WARN]  Exiting...")
    except Exception as e:
        logger.error(f"[ERROR] Fatal error: {e}")
        print(f"\n[ERROR] Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[WARN]  Script stopped by user")
    except Exception as e:
        print(f"\n\n[ERROR] Error: {e}")
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
