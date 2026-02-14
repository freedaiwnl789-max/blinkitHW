"""
Telegram Bot Service
- Send product availability notifications to Telegram channel
"""

import logging
import aiohttp

logger = logging.getLogger(__name__)


class TelegramBot:
    """Send messages to Telegram channel"""
    
    def __init__(self, bot_token: str, channel_id: str):
        """
        Initialize Telegram bot
        
        Args:
            bot_token: Telegram bot token (from @BotFather)
            channel_id: Telegram channel ID (e.g., @mychannel or -100123456789)
        """
        self.bot_token = bot_token
        self.channel_id = channel_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
    
    async def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send a text message to the Telegram channel
        
        Args:
            message: Message text (supports HTML formatting)
            parse_mode: HTML or Markdown formatting
        
        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.channel_id,
                "text": message,
                "parse_mode": parse_mode
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status == 200:
                        logger.info("✓ Telegram message sent successfully")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"Telegram send failed (status {response.status}): {error_text}")
                        return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False
    
    async def send_product_notification(self, product_name: str, product_url: str, location_name: str) -> bool:
        """
        Send a formatted product availability notification
        
        Args:
            product_name: Name of the product
            product_url: URL to the product
            location_name: Delivery location name
        
        Returns:
            True if successful, False otherwise
        """
        # Use only Telegram-supported HTML tags (avoid <h1>, etc.)
        message = (
            f"<b>🎉 Product Available!</b>\n\n"
            f"<b>Product:</b> {product_name}\n\n"
            f"📍<b>Location:</b> <b>{location_name}</b>\n\n"
            f"<b>Link:</b>\n"
            f"<a href=\"{product_url}\">Open on Blinkit</a>"
        )

        result = await self.send_message(message)
        if not result:
            logger.warning("Telegram notification failed — check bot token, channel id, and that the bot is added to the channel/group.")
        return result
