#!/usr/bin/env python3
"""
Simple Product Watcher
- Ask user for product URL
- Monitor if product is "Coming Soon" or available
- Auto-purchase when available
"""

import asyncio
import json
import logging
import sys
import os
import difflib
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file (specify absolute path)
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# Platform-specific sound alert
if sys.platform == "win32":
    import winsound

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.auth import BlinkitAuth
from src.order.blinkit_order import BlinkitOrder
from src.telegram.service import TelegramBot

# Status file location
STATUS_FILE = Path("product_status.json")

# ANSI color code for product names
PRODUCT_COLOR = '\033[95m'  # Magenta
RESET_COLOR = '\033[0m'

def colorize_product(name):
    """Wrap product name with color codes"""
    return f"{PRODUCT_COLOR}{name}{RESET_COLOR}"

def play_alert_sound():
    """Play an alert sound when product is available"""
    try:
        if sys.platform == "win32":
            # Windows: play a beep at 1000 Hz for 1 second
            # winsound.Beep(1000, 500)
            # Play it twice for emphasis
            import time
            time.sleep(0.2)
            # winsound.Beep(1000, 1000)
        else:
            # On other platforms, use system beep
            print('\a', end='', flush=True)
    except Exception as e:
        logger.debug(f"Failed to play alert sound: {e}")


class OrdinalDateFormatter(logging.Formatter):
    """Custom formatter with ordinal dates and colored output"""
    
    # ANSI color codes
    LEVEL_COLORS = {
        'DEBUG': {
            'time': '\033[36m',      # Cyan for time
            'level': '\033[36m',     # Cyan for level
            'message': '\033[36m'    # Cyan for message
        },
        'INFO': {
            'time': '\033[94m',      # Blue for time
            'level': '\033[92m',     # Green for level
            'message': '\033[92m'    # Green for message
        },
        'WARNING': {
            'time': '\033[94m',      # Blue for time
            'level': '\033[93m',     # Yellow for level
            'message': '\033[93m'    # Yellow for message
        },
        'ERROR': {
            'time': '\033[94m',      # Blue for time
            'level': '\033[91m',     # Red for level
            'message': '\033[91m'    # Red for message
        },
        'CRITICAL': {
            'time': '\033[94m',      # Blue for time
            'level': '\033[95m',     # Magenta for level
            'message': '\033[95m'    # Magenta for message
        }
    }
    
    RESET = '\033[0m'
    
    def format(self, record):
        # Convert timestamp to ordinal date format
        dt = datetime.fromtimestamp(record.created)
        day = dt.day
        month = dt.strftime('%b')
        year = dt.year
        time_str = dt.strftime('%I:%M:%S %p')
        
        # Add ordinal suffix to day
        if 10 <= day % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10, 'th')
        
        ordinal_date = f"{day}{suffix} {month} {year} {time_str}"
        
        # Get colors for this level
        colors = self.LEVEL_COLORS.get(record.levelname, self.LEVEL_COLORS['INFO'])
        
        # Apply colors to each component
        colored_time = f"{colors['time']}{ordinal_date}{self.RESET}"
        colored_level = f"{colors['level']}{record.levelname}{self.RESET}"
        colored_message = f"{colors['message']}{record.getMessage()}{self.RESET}"
        
        # Format: [colored_time] - colored_level - colored_message
        log_message = f"{colored_time} - {colored_level} - {colored_message}"
        
        return log_message


# Configure logging with custom formatter
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(OrdinalDateFormatter())

file_handler = logging.FileHandler('product_watcher.log', encoding='utf-8')
file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%d %b %Y %I:%M %p')
file_handler.setFormatter(file_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
    force=True
)
logger = logging.getLogger(__name__)


class ProductWatcher:
    def __init__(self, product_url, latitude, longitude, check_interval=30, location_label="Home", continue_on_out_of_stock=False, telegram_bot_token=None, telegram_channel_id=None):
        """
        Initialize the product watcher
        
        Args:
            product_url: Full Blinkit product URL
            latitude: Delivery location latitude
            longitude: Delivery location longitude
            check_interval: Time between checks in seconds
            location_label: Saved address label to select (default 'Home')
            continue_on_out_of_stock: Keep monitoring if product goes out of stock (default False)
            telegram_bot_token: Telegram bot token for notifications
            telegram_channel_id: Telegram channel ID for notifications
        """
        self.product_url = product_url
        self.latitude = latitude
        self.longitude = longitude
        self.check_interval = check_interval
        self.query_count = 0
        self.auth = None
        self.order = None
        self.product_id = self.extract_product_id(product_url)
        self.expected_product_name = None
        # Label of the saved address to select via site UI (e.g., 'Home')
        self.location_label = location_label or "Home"
        # Continue refreshing if product goes out of stock
        self.continue_on_out_of_stock = continue_on_out_of_stock
        
        # Telegram bot configuration
        self.telegram_bot = None
        if telegram_bot_token and telegram_channel_id:
            self.telegram_bot = TelegramBot(telegram_bot_token, telegram_channel_id)

    def extract_product_id(self, url):
        """Extract product ID from URL"""
        try:
            return url.split("prid/")[-1]
        except:
            return None

    async def get_product_title(self, page):
        """Try multiple selectors/meta tags to extract a reliable product title."""
        # Use page.evaluate to read DOM properties directly to avoid locator wait issues
        try:
            try:
                meta = await page.evaluate("() => { const m = document.querySelector(\"meta[property='og:title']\"); return m ? m.getAttribute('content') : null; }")
                if meta:
                    return meta.strip()
            except Exception:
                pass

            selectors = ["h1", ".product-title", ".productName", "[data-testid='product-title']", ".pdp__title"]
            for sel in selectors:
                try:
                    script = f"() => {{ const el = document.querySelector('{sel}'); return el ? (el.innerText || el.textContent) : null; }}"
                    text = await page.evaluate(script)
                    if text:
                        return text.strip()
                except Exception:
                    continue

            try:
                title = await page.title()
                if title:
                    return title.strip()
            except Exception:
                pass

        except Exception:
            # Any unexpected Playwright errors should not crash the watcher
            logger.debug("get_product_title: extraction failed, returning Unknown")

        return "Unknown"

    async def check_stock_status(self, page):
        """Check if product is out of stock"""
        try:
            # Common out of stock indicators
            out_of_stock_indicators = [
                "text=Out of Stock",
                "text=Out of stock",
                "text=Sold Out",
                "text=Sold out",
                "text=Not Available",
                "text=Not available",
                "[class*='outofstock' i]",
                "[class*='out-of-stock' i]",
                "[class*='soldout' i]",
                "[class*='sold-out' i]"
            ]
            
            for indicator in out_of_stock_indicators:
                try:
                    if await page.is_visible(indicator):
                        return True
                except Exception:
                    continue
            
            # Also check if ADD button is disabled
            try:
                add_button = await page.query_selector("text=ADD")
                if add_button:
                    is_disabled = await add_button.evaluate("el => el.disabled || el.getAttribute('disabled') !== null || el.className.includes('disabled')")
                    if is_disabled:
                        return True
            except Exception:
                pass
            
            return False
        except Exception as e:
            logger.debug(f"check_stock_status error: {e}")
            return False

    async def get_cart_product_name(self, page):
        """Extract product name from cart view"""
        try:
            # Try common cart item selectors
            selectors = [
                ".cart-item-name",
                ".product-name",
                "[data-testid='cart-item-name']",
                ".CartItem__ProductName",
                ".CartItemCard__ProductName",
                ".cart-product-title",
                ".item-name",
                ".productName"
            ]
            
            for sel in selectors:
                try:
                    script = f"() => {{ const el = document.querySelector('{sel}'); return el ? (el.innerText || el.textContent) : null; }}"
                    text = await page.evaluate(script)
                    if text:
                        return text.strip()
                except Exception:
                    continue
            
            # Try getting product info from cart item container - more flexible approach
            try:
                script = """() => {
                    // Try multiple container patterns
                    const containers = [
                        ...document.querySelectorAll('[class*="CartItem"]:not([class*="Divider"])'),
                        ...document.querySelectorAll('[class*="cart-item"]'),
                        ...document.querySelectorAll('[data-testid*="cart"]'),
                    ];
                    
                    if (containers.length > 0) {
                        const container = containers[0];
                        
                        // Try to find product name in various places
                        // 1. Look for headings
                        let heading = container.querySelector('h1, h2, h3, h4, h5, h6');
                        if (heading) return (heading.innerText || heading.textContent).trim();
                        
                        // 2. Look for text in strong/bold elements
                        let strong = container.querySelector('strong, [class*="title"], [class*="name"]');
                        if (strong) return (strong.innerText || strong.textContent).trim();
                        
                        // 3. Get all text and extract first meaningful line
                        let allText = container.innerText || container.textContent;
                        if (allText) {
                            let lines = allText.split('\\n').filter(l => l.trim().length > 10);
                            if (lines.length > 0) return lines[0].trim();
                        }
                    }
                    return null;
                }"""
                text = await page.evaluate(script)
                if text and text != "null":
                    return text.strip()
            except Exception as e:
                logger.debug(f"Container extraction failed: {e}")
            
            # Last resort: try to find any product-related text in the page
            try:
                script = """() => {
                    // Look for any element containing product-like text
                    const allElements = document.querySelectorAll('[class*="product"], [class*="item"], [class*="cart"]');
                    for (let el of allElements) {
                        const text = (el.innerText || el.textContent || '').trim();
                        // Look for text that's likely a product name (reasonable length, not just numbers)
                        if (text.length > 15 && text.length < 500 && !text.match(/^\\d+\\s*(x|\\+|Rs)/i)) {
                            return text.split('\\n')[0].trim();
                        }
                    }
                    return null;
                }"""
                text = await page.evaluate(script)
                if text and text != "null":
                    return text.strip()
            except Exception as e:
                logger.debug(f"Last resort extraction failed: {e}")
            
        except Exception as e:
            logger.debug(f"get_cart_product_name: extraction failed: {e}")
        
        return "Unknown"

    def write_status(self, status, details=None):
        """Write status to JSON file"""
        status_data = {
            "product_url": self.product_url,
            "product_id": self.product_id,
            "location": {
                "latitude": self.latitude,
                "longitude": self.longitude
            },
            "status": status,
            "timestamp": datetime.now().isoformat(),
            "query_count": self.query_count,
            "details": details or {},
            "action_needed": status == "available"
        }
        
        try:
            with open(STATUS_FILE, 'w') as f:
                json.dump(status_data, f, indent=2)
            logger.info(f"Status: {status}")
            return True
        except Exception as e:
            logger.error(f"Error writing status file: {e}")
            return False

    async def check_product_status(self):
        """Check if product is available or coming soon"""
        try:
            self.query_count += 1
            logger.info(f"[CHECK #{self.query_count}] Navigating to product URL...")
            
            # Navigate to product URL
            try:
                await self.order.page.goto(self.product_url, wait_until="domcontentloaded", timeout=30000)
            except Exception as e:
                logger.warning(f"Navigation took longer: {e}")
            
            await asyncio.sleep(2)
            
            # Get product details from page
            product_name = "Unknown"
            coming_soon_status = "Unknown"
            
            try:
                # Extract product name using robust extractor
                try:
                    product_name = await self.get_product_title(self.order.page)
                    logger.info(f"[PRODUCT] Name: {colorize_product(product_name)}")
                    # Store for verification during purchase if not already set
                    if not self.expected_product_name:
                        self.expected_product_name = product_name
                        logger.info(f"[EXPECTED] Remembered product name for verification: {colorize_product(self.expected_product_name)}")
                except Exception:
                    # Ignore extraction errors and continue to status checks
                    pass

                # Check for "Coming Soon" text
                if await self.order.page.is_visible("text=Coming Soon"):
                    coming_soon_status = "Coming Soon"
                else:
                    coming_soon_status = "Available"
                    
                logger.info(f"[STATUS] {coming_soon_status}")
                
            except Exception as e:
                logger.warning(f"Error extracting product details: {e}")
            
            # Check if product is AVAILABLE (no Coming Soon, has ADD button)
            is_coming_soon = coming_soon_status == "Coming Soon"
            is_add_to_cart = await self.order.page.is_visible("text=ADD")
            
            logger.info(f"Coming Soon visible: {is_coming_soon}, Add button visible: {is_add_to_cart}")
            
            if is_add_to_cart and not is_coming_soon:
                # Product is AVAILABLE
                logger.info(f"[AVAILABLE] Product {colorize_product(product_name)} is now AVAILABLE!")
                
                # Play alert sound
                play_alert_sound()
                
                self.write_status("available", {
                    "message": "Product is available for purchase!",
                    "product_name": product_name,
                    "product_id": self.product_id,
                    "found_at": datetime.now().isoformat()
                })
                return True
                    
            elif is_coming_soon:
                # Still coming soon
                logger.info(f"[WAITING] Product {colorize_product(product_name)} is still Coming Soon...")
                self.write_status("coming_soon", {
                    "message": "Product still Coming Soon in your location",
                    "product_name": product_name,
                    "last_checked": datetime.now().isoformat()
                })
                return False
            else:
                logger.warning("[UNKNOWN] Could not determine product status")
                self.write_status("unknown", {
                    "message": "Could not determine if product is available or coming soon",
                    "product_name": product_name
                })
                return False
                
        except Exception as e:
            logger.error(f"Error checking product: {e}")
            self.write_status("error", {"error": str(e)})
            return False

    async def watch(self, max_checks=None):
        """
        Monitor product until available
        
        Args:
            max_checks: Max checks before giving up (None = infinite)
        """
        logger.info("=" * 70)
        logger.info("PRODUCT WATCHER - Wait for Coming Soon to be Available")
        logger.info("=" * 70)
        logger.info(f"Product URL: {self.product_url}")
        logger.info(f"Check interval: {self.check_interval} seconds")
        logger.info(f"Max checks: {max_checks if max_checks else 'Unlimited'}")
        logger.info("-" * 70)
        
        # Initialize browser and auth
        try:
            logger.info("Initializing Blinkit authentication...")
            if self.latitude and self.longitude:
                logger.info(f"Using location: Latitude {self.latitude}, Longitude {self.longitude}")
            else:
                logger.info("No coordinates provided — will select saved address via site UI (Home)")
            self.auth = BlinkitAuth(headless=False)  # Show browser
            await self.auth.start_browser()

            # If coordinates not provided, try selecting saved 'Home' address via the location bar UI
            if not (self.latitude and self.longitude):
                try:
                    # Selector for the location bar container (two classes)
                    loc_sel = "div.LocationBar__Container-sc-x8ezho-6.gcLVHe"
                    # Fallback: partial class match
                    if await self.auth.page.is_visible(loc_sel):
                        await self.auth.page.click(loc_sel)
                        await asyncio.sleep(1)
                        # Look for a saved address labeled per user preference
                        location_selector = f"text={self.location_label}"
                        if await self.auth.page.is_visible(location_selector):
                            await self.auth.page.click(location_selector)
                            await asyncio.sleep(2)
                            logger.info(f"Selected saved address: {self.location_label}")
                            # Move cursor to My Cart button to dismiss location selector
                            if await self.auth.page.is_visible("text=My Cart"):
                                await self.auth.page.click("text=My Cart")
                                await asyncio.sleep(1)
                                logger.info("Moved to My Cart")
                        else:
                            logger.info("'Home' address not found in location options")
                    else:
                        # Try a broader selector
                        try:
                            broad = "[class*='LocationBar__Container']"
                            if await self.auth.page.is_visible(broad):
                                await self.auth.page.click(broad)
                                await asyncio.sleep(1)
                                location_selector = f"text={self.location_label}"
                                if await self.auth.page.is_visible(location_selector):
                                    await self.auth.page.click(location_selector)
                                    await asyncio.sleep(2)
                                    logger.info(f"Selected saved address: {self.location_label} (broad selector)")
                                    # Move cursor to My Cart button to dismiss location selector
                                    if await self.auth.page.is_visible("text=My Cart"):
                                        await self.auth.page.click("text=My Cart")
                                        await asyncio.sleep(1)
                                        logger.info("Moved to My Cart")
                                else:
                                    logger.info("'Home' address not found after opening location bar")
                        except Exception:
                            logger.debug("Broad location selector failed")
                except Exception as e:
                    logger.warning(f"Location UI selection failed: {e}")
            else:
                # If coordinates provided, set geolocation in context
                try:
                    if self.auth.context:
                        await self.auth.context.set_geolocation({"latitude": self.latitude, "longitude": self.longitude})
                        await self.auth.context.grant_permissions(["geolocation"])
                except Exception as e:
                    logger.warning(f"Failed to set geolocation: {e}")
            
            if not await self.auth.is_logged_in():
                logger.error("Not logged in!")
                await self.auth.close()
                return False
            
            logger.info("[OK] Logged in successfully")
            logger.info(f"[OK] Location set to: Lat {self.latitude}, Lon {self.longitude}")
            self.order = BlinkitOrder(self.auth.page)
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False
        
        # Initial status
        self.write_status("monitoring", {"started_at": datetime.now().isoformat()})
        
        check_num = 0
        start_time = datetime.now()
        
        try:
            while True:
                if max_checks and check_num >= max_checks:
                    logger.info(f"Max checks ({max_checks}) reached. Stopping.")
                    self.write_status("stopped", {"reason": "Max checks reached"})
                    return False
                
                check_num += 1
                
                # Check product status
                is_available = await self.check_product_status()
                
                if is_available:
                    elapsed = datetime.now() - start_time
                    logger.info(f"[SUCCESS] Product became available after {elapsed} ({check_num} checks)")
                    
                    # Check if product is in stock before attempting purchase
                    is_out_of_stock = await self.check_stock_status(self.order.page)
                    
                    if is_out_of_stock:
                        logger.warning("[OUT OF STOCK] Product is out of stock!")
                        if self.continue_on_out_of_stock:
                            logger.info("[CONTINUE MODE] Product out of stock but continuing to monitor...")
                            self.write_status("out_of_stock_monitoring", {
                                "message": "Product went out of stock but continuing to monitor",
                                "product_name": self.expected_product_name,
                                "timestamp": datetime.now().isoformat(),
                                "checks_so_far": check_num
                            })
                            # Wait before next check
                            logger.info(f"Waiting {self.check_interval} seconds before next check...")
                            await asyncio.sleep(self.check_interval)
                            continue  # Skip auto-purchase and go to next check
                        else:
                            logger.error("[ABORT] Stopping due to product going out of stock")
                            self.write_status("out_of_stock", {
                                "message": "Product went out of stock",
                                "product_name": self.expected_product_name,
                                "timestamp": datetime.now().isoformat()
                            })
                            return False
                    
                    # Product is in stock - proceed with auto-purchase
                    logger.info("Starting auto-purchase...")
                    success = await self.auto_purchase()
                    
                    if success:
                        logger.info("[COMPLETE] Purchase completed!")
                        self.write_status("purchased", {
                            "completed_at": datetime.now().isoformat(),
                            "total_checks": check_num
                        })
                        return True
                    else:
                        logger.warning("Auto-purchase failed. Manual intervention needed.")
                        self.write_status("available", {
                            "message": "Product available but auto-purchase failed",
                            "action": "Manual purchase needed"
                        })
                        return False
                
                # Wait before next check
                logger.info(f"Waiting {self.check_interval} seconds before next check...")
                await asyncio.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("\n[STOPPED] Watcher stopped by user")
            elapsed = datetime.now() - start_time
            self.write_status("stopped", {
                "reason": "User interrupted",
                "checks_performed": check_num,
                "duration": str(elapsed)
            })
            return False
        
        finally:
            if self.auth:
                try:
                    if hasattr(self.auth, 'close'):
                        await self.auth.close()
                    logger.info("Browser closed")
                except Exception as e:
                    logger.debug(f"Browser close error: {e}")

    async def auto_purchase(self):
        """Automatically add to cart and proceed to checkout"""
        try:
            logger.info("Step 1: Verifying product details before adding to cart...")
            
            # Check if telegram bot is configured
            if self.telegram_bot:
                logger.info(f"[INFO] Telegram bot is configured and ready")
            else:
                logger.info(f"[INFO] Telegram bot is NOT configured")
            
            # Verify we have the correct product on screen using fuzzy matching
            product_name = await self.get_product_title(self.order.page)
            logger.info(f"[VERIFY] Product on screen: {colorize_product(product_name)}")

            if self.expected_product_name:
                logger.info(f"[VERIFY] Expected product: {colorize_product(self.expected_product_name)}")
                # Compute similarity
                ratio = difflib.SequenceMatcher(None, (self.expected_product_name or "").lower(), (product_name or "").lower()).ratio()
                logger.info(f"[MATCH] Similarity ratio: {ratio:.2f}")

                # Decision logic:
                # - If exact/very close match -> proceed automatically
                # - If moderate match (>= 0.70) -> proceed automatically without confirmation
                # - If low match -> abort to avoid wrong purchase
                if ratio >= 0.70:
                    logger.info("[AUTO] Good match (similarity >= 0.70) — proceeding automatically")
                else:
                    logger.warning("[ABORT] Low-confidence match — aborting auto-purchase to avoid wrong product")
                    self.write_status("available", {"message": "Aborted due to product name mismatch", "product_name": product_name, "similarity": ratio})
                    return False
            
            logger.info("Step 2: Adding product to cart...")
            
            # Make sure we're clicking the right ADD button for this product
            add_selectors = ["text=ADD", "text=Add", ".add-to-cart", "button.add", "button:has-text('Add')"]
            clicked = False
            for sel in add_selectors:
                try:
                    if await self.order.page.is_visible(sel):
                        await self.order.page.click(sel)
                        await asyncio.sleep(2)
                        logger.info(f"[OK] Clicked ADD selector: {sel}")
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                logger.error("ADD button not found with known selectors")
                return False
            
            logger.info("Step 3: Opening cart...")
            # Navigate to cart or open cart drawer
            if await self.order.page.is_visible("text=My Cart"):
                await self.order.page.click("text=My Cart")
                await asyncio.sleep(2)
                logger.info("[OK] Cart opened")
            
            # Send Telegram notification immediately after cart is opened
            if self.telegram_bot:
                logger.info("Step 3a: Sending Telegram notification...")
                product_name = self.expected_product_name or "Unknown Product"
                
                try:
                    telegram_success = await self.telegram_bot.send_product_notification(
                        product_name=product_name,
                        product_url=self.product_url,
                        location_name=self.location_label
                    )
                    
                    if telegram_success:
                        logger.info("[OK] Telegram notification sent successfully")
                    else:
                        logger.warning("[WARN] Telegram notification failed to send")
                except Exception as e:
                    logger.error(f"[ERROR] Telegram notification error: {e}")
            
            logger.info("Step 3b: Verifying product in cart...")
            # Extract product name from cart and verify it matches expected product
            cart_product_name = await self.get_cart_product_name(self.order.page)
            logger.info(f"[CART] Product in cart: {colorize_product(cart_product_name)}")
            
            if self.expected_product_name and cart_product_name != "Unknown":
                logger.info(f"[VERIFY] Expected product: {colorize_product(self.expected_product_name)}")
                # Compute similarity
                ratio = difflib.SequenceMatcher(None, (self.expected_product_name or "").lower(), (cart_product_name or "").lower()).ratio()
                logger.info(f"[MATCH] Cart product similarity ratio: {ratio:.2f}")
                
                if ratio < 0.70:
                    logger.warning(f"[MISMATCH] Product in cart does not match expected product!")
                    logger.warning(f"Expected {colorize_product(self.expected_product_name)} but found {colorize_product(cart_product_name)} (similarity={ratio:.2f})")
                    logger.info("Proceeding to checkout anyway (auto-mode)")
                else:
                    logger.info(f"[OK] Cart product matches expected product (similarity={ratio:.2f})")
            
            logger.info("Step 4: Clicking on cart button to open cart drawer...")
            # Click on the cart button with class CartButton__Container-sc-1fuy2nj-3 eOczDn
            cart_button_selectors = [
                ".CartButton__Container-sc-1fuy2nj-3",
                "[class*='CartButton__Container']",
                "button[class*='CartButton']"
            ]
            
            cart_button_clicked = False
            for sel in cart_button_selectors:
                try:
                    if await self.order.page.is_visible(sel):
                        await self.order.page.click(sel)
                        await asyncio.sleep(2)
                        logger.info(f"[OK] Clicked cart button: {sel}")
                        cart_button_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Cart button selector {sel} failed: {e}")
                    continue
            
            if not cart_button_clicked:
                logger.warning("Could not click cart button")
            
            logger.info("Step 5: Clicking Proceed to pay button to go to checkout...")
            
            # Scroll down to ensure the Proceed to pay button is visible
            try:
                await self.order.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)
                logger.info("[OK] Scrolled to bottom of page")
            except Exception as e:
                logger.debug(f"Scroll failed: {e}")
            
            # Click "Proceed to pay" button which redirects to checkout
            # Try various selectors for the button
            proceed_to_pay_selectors = [
                "button:has-text('Proceed to Pay')",
            ]

            proceed_clicked = False
            for sel in proceed_to_pay_selectors:
                try:
                    if await self.order.page.is_visible(sel):
                        # Scroll the element into view before clicking
                        await self.order.page.locator(sel).first.scroll_into_view_if_needed()
                        await asyncio.sleep(0.5)
                        await self.order.page.click(sel)
                        await asyncio.sleep(3)
                        logger.info(f"[OK] Clicked: {sel}")
                        proceed_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Selector {sel} failed: {e}")
                    continue

            if not proceed_clicked:
                logger.warning("Could not click Proceed to pay button - trying to find all buttons on page")
                # Try to find any button with payment-related text
                try:
                    all_buttons = await self.order.page.query_selector_all("button")
                    logger.info(f"[DEBUG] Found {len(all_buttons)} buttons on page")
                    for i, btn in enumerate(all_buttons):
                        btn_text = await btn.text_content()
                        logger.info(f"[DEBUG] Button {i}: {btn_text}")
                except Exception as e:
                    logger.debug(f"Could not enumerate buttons: {e}")

            # Wait for redirect and ensure we're on checkout page
            await asyncio.sleep(2)
            current_url = self.order.page.url
            logger.info(f"Current page URL: {current_url}")

            logger.info("Step 6: Selecting Cash payment method...")
            # Try common selectors for Cash / COD payment option
            # Based on HTML: <div role="button" aria-label="Cash" title="Cash">
            cash_selectors = [
                "[aria-label='Cash']",
                "div[role='button'][aria-label='Cash']",
                "[title='Cash']",
                "h5:has-text('Cash')",
                "text=Cash",
                "[class*='cod']",
                "[class*='cash']"
            ]

            cash_clicked = False
            for sel in cash_selectors:
                try:
                    if await self.order.page.is_visible(sel):
                        await self.order.page.click(sel)
                        await asyncio.sleep(1)
                        logger.info(f"[OK] Selected payment option: {sel}")
                        cash_clicked = True
                        break
                except Exception as e:
                    logger.debug(f"Cash selector {sel} failed: {e}")
                    continue

            if not cash_clicked:
                logger.warning("Could not automatically select Cash payment option")

            logger.info("Step 7: Clicking Pay Now button...")
            # Try to click Pay Now / Pay now button
            pay_selectors = [
                "button:has-text('Pay Now')",
                "button:has-text('Pay now')",
                "text=Pay Now",
                "text=Pay now",
                "button:has-text('Place Order')",
                "text=Place Order"
            ]

            pay_clicked = False
            for sel in pay_selectors:
                try:
                    if await self.order.page.is_visible(sel):
                        await self.order.page.click(sel)
                        await asyncio.sleep(2)
                        logger.info(f"[OK] Clicked payment button: {sel}")
                        pay_clicked = True
                        break
                except Exception:
                    continue

            if not pay_clicked:
                logger.warning("Pay button not found — please complete payment manually on the checkout page")
                # Give user some time to complete manual payment
                logger.info("Waiting 120 seconds for you to complete payment manually...")
                await asyncio.sleep(120)
            else:
                logger.info("Payment button clicked; waiting briefly for confirmation...")
                await asyncio.sleep(5)

            logger.info("[SUCCESS] Checkout steps attempted/completed")
            return True
            
        except Exception as e:
            logger.error(f"Auto-purchase error: {e}")
            return False


async def main():
    """Main entry point"""
    
    # Ask user for product URL and location
    print("\n" + "=" * 70)
    print("BLINKIT PRODUCT WATCHER")
    print("=" * 70)
    print("\nThis script will:")
    print("1. Monitor a product URL for availability in your SPECIFIC LOCATION")
    print("2. Wait if it's 'Coming Soon'")
    print("3. Auto-purchase when available")
    print("\nExample URL: https://blinkit.com/prn/x/prid/746548")
    print("-" * 70)
    
    product_url = input("\nEnter product URL: ").strip()
    
    if not product_url.startswith("http"):
        logger.error("Invalid URL. Must start with http")
        return
    
    if "blinkit.com" not in product_url:
        logger.error("Invalid URL. Must be a Blinkit product URL")
        return
    
    # Use site UI to select saved address instead of asking for coordinates
    print("\nUsing site UI to select a saved address via the site UI. No latitude/longitude input required.")

    # Ask for the saved-address label to select (default: Home)
    location_label = input("\nEnter saved address label to select (default 'Home'): ").strip() or "Home"

    # Ask for check interval
    try:
        check_interval = int(input("\nEnter check interval in seconds (default 30): ").strip() or "30")
    except ValueError:
        check_interval = 30

    # Ask if user wants to keep monitoring even if product goes out of stock
    continue_on_oos = input("\nContinue refreshing if product goes out of stock? (y/N): ").strip().lower() in ('y', 'yes')

    # Load Telegram credentials from environment variables
    telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    telegram_channel_id = os.getenv("TELEGRAM_CHANNEL_ID")

    logger.info(f"Product URL: {product_url}")
    logger.info(f"Location: using site-saved address ('{location_label}') via UI")
    logger.info(f"Check interval: {check_interval} seconds")
    logger.info(f"Continue on out-of-stock: {'YES - will keep refreshing' if continue_on_oos else 'NO - will stop'}")
    if telegram_bot_token and telegram_channel_id:
        logger.info(f"Telegram notifications: ENABLED (Channel: {telegram_channel_id})")
    else:
        logger.info("Telegram notifications: DISABLED (set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in .env)")

    # Start watching (no coordinates provided — watcher will try to select given saved address)
    watcher = ProductWatcher(
        product_url, 
        None, 
        None, 
        check_interval, 
        location_label, 
        continue_on_oos,
        telegram_bot_token=telegram_bot_token,
        telegram_channel_id=telegram_channel_id
    )
    success = await watcher.watch(max_checks=None)  # Infinite checks
    
    if success:
        logger.info("\n[SUCCESS] Product purchased successfully!")
    else:
        logger.info("\n[INFO] Watcher stopped. Product not yet available.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
