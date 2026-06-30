import os
import sys
import logging
import io
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from PIL import Image

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
def get_token():
    """Get bot token from environment variables."""
    token = os.environ.get('BOT_TOKEN')
    if not token:
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("❌ No BOT_TOKEN found in environment variables!")
        logger.error("Please add BOT_TOKEN to your Railway Variables.")
        sys.exit(1)
    return token

TOKEN = get_token()
logger.info("✅ Bot token loaded successfully!")

# Try to get API key (optional - for free version we'll use Pollinations API)
API_KEY = os.environ.get('OPENAI_API_KEY') or os.environ.get('GEMINI_API_KEY')

# Store user settings
user_settings = {}

# Image generation settings
DEFAULT_STYLE = "digital art, highly detailed, 4k"
STYLES = {
    'realistic': 'photorealistic, 8k, highly detailed, natural lighting',
    'anime': 'anime style, studio ghibli inspired, vibrant colors, detailed',
    'digital_art': 'digital art, highly detailed, 4k, vibrant colors',
    'oil_painting': 'oil painting, renaissance style, textured, dramatic lighting',
    'watercolor': 'watercolor painting, soft colors, artistic, dreamy',
    'cartoon': 'cartoon style, pixar inspired, colorful, playful',
    'cyberpunk': 'cyberpunk style, neon lights, futuristic, dark atmosphere',
    'fantasy': 'fantasy art, magical, ethereal, detailed',
    'minimalist': 'minimalist, clean lines, simple, modern',
    'sketch': 'pencil sketch, black and white, artistic, detailed'
}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message."""
    user = update.effective_user
    welcome_text = f"""
🎨 **Welcome to ImageGenie1Bot, {user.first_name}!**

I'm your AI image generator. Just send me a text description, and I'll create an image for you!

**Commands:**
/start - Show this welcome message
/help - Show all commands
/style - Choose art style
/settings - View your current settings
/generate [prompt] - Generate an image

**Examples:**
`A cyberpunk cat wearing a VR headset`
`A majestic dragon flying over a futuristic city`
`A beautiful landscape with mountains and sunset`

💡 **Tip:** Be specific for better results!
"""
    await update.message.reply_text(welcome_text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a help message."""
    help_text = """
🖼️ **How to generate an image:**

1️⃣ Send me any descriptive text
2️⃣ I'll generate an image based on your prompt
3️⃣ Get your image instantly!

**Commands:**
/start - Welcome message
/help - Show this help message
/style - Choose art style
/settings - View your current settings
/generate [prompt] - Generate with specific prompt

**Style Options:**
• Realistic • Anime • Digital Art
• Oil Painting • Watercolor • Cartoon
• Cyberpunk • Fantasy • Minimalist • Sketch

**Examples:**
`/generate A magical forest with glowing mushrooms`
`A steampunk airship floating above clouds`

💡 **Pro tip:** Use /style to change the art style!
"""
    await update.message.reply_text(help_text)


async def style_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show style selection menu."""
    keyboard = []
    row = []
    for idx, (style_key, style_name) in enumerate(STYLES.items()):
        # Format style name for display
        display_name = style_key.replace('_', ' ').title()
        row.append(InlineKeyboardButton(display_name, callback_data=f"style_{style_key}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="style_cancel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🎨 **Select an art style:**\n\n"
        "Choose your preferred style for image generation.",
        reply_markup=reply_markup
    )


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user settings."""
    user_id = update.effective_user.id
    settings = user_settings.get(user_id, {})
    style = settings.get('style', 'digital_art')
    style_display = style.replace('_', ' ').title()
    
    settings_text = f"""
⚙️ **Your Settings:**

🎨 Style: {style_display}
📏 Size: 1024x1024
🔄 Quality: Standard

**Commands:**
/style - Change art style
/help - Get more help
"""
    await update.message.reply_text(settings_text)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses."""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    data = query.data
    
    if data == "style_cancel":
        await query.edit_message_text("❌ Style selection cancelled.")
        return
    
    if data.startswith("style_"):
        style_key = data.replace("style_", "")
        if style_key in STYLES:
            # Save user's style preference
            if user_id not in user_settings:
                user_settings[user_id] = {}
            user_settings[user_id]['style'] = style_key
            
            style_display = style_key.replace('_', ' ').title()
            await query.edit_message_text(
                f"✅ **Style set to: {style_display}**\n\n"
                f"Now send me a prompt to generate an image in this style!\n"
                f"Or use /generate [your prompt]"
            )


async def generate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /generate command."""
    # Get the prompt from the command
    prompt = ' '.join(context.args)
    
    if not prompt:
        await update.message.reply_text(
            "❌ Please provide a prompt!\n\n"
            "Example: `/generate A beautiful sunset over mountains`"
        )
        return
    
    # Call the image generation function
    await generate_image(update, context, prompt)


async def generate_image(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str = None) -> None:
    """Generate an image from text prompt."""
    # If prompt not provided, use the message text
    if prompt is None:
        prompt = update.message.text
    
    user_id = update.effective_user.id
    user = update.effective_user
    
    # Get user's style preference
    settings = user_settings.get(user_id, {})
    style = settings.get('style', 'digital_art')
    style_prompt = STYLES.get(style, STYLES['digital_art'])
    
    # Combine prompt with style
    full_prompt = f"{prompt}, {style_prompt}"
    
    # Send processing message
    processing_msg = await update.message.reply_text(
        f"🎨 **Generating your image...**\n\n"
        f"📝 Prompt: `{prompt}`\n"
        f"🎭 Style: {style.replace('_', ' ').title()}\n"
        f"⏳ This may take a moment..."
    )
    
    try:
        # Use Pollinations API (free, no API key required)
        # This is a free alternative that works without any API key
        encoded_prompt = full_prompt.replace(' ', '%20')
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1024&height=1024&nologo=true"
        
        # Download the image
        async with aiohttp.ClientSession() as session:
            async with session.get(image_url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    
                    # Send the image back to the user
                    await update.message.reply_photo(
                        photo=io.BytesIO(image_data),
                        caption=f"✅ **Image Generated!**\n\n"
                                f"📝 Prompt: `{prompt}`\n"
                                f"🎭 Style: {style.replace('_', ' ').title()}"
                    )
                    await processing_msg.delete()
                else:
                    raise Exception(f"API returned status {response.status}")
                    
    except Exception as e:
        logger.error(f"Image generation failed for user {user.id}: {e}")
        
        # Try fallback API
        try:
            await processing_msg.edit_text("🔄 Trying alternative API...")
            
            # Fallback to another free API
            fallback_url = f"https://api.unsplash.com/photos/random?query={prompt.replace(' ', '%20')}&orientation=landscape"
            # Note: Unsplash requires API key, so this is just a placeholder
            
            # If both fail, send error
            await processing_msg.edit_text(
                f"❌ **Sorry, I couldn't generate your image.**\n\n"
                f"Error: {str(e)}\n\n"
                f"💡 **Tips:**\n"
                f"• Try a simpler prompt\n"
                f"• Check your internet connection\n"
                f"• Use /help for guidance"
            )
        except Exception as fallback_error:
            await processing_msg.edit_text(
                f"❌ **Image generation failed.**\n\n"
                f"Please try again with a different prompt.\n"
                f"Use /help for more information."
            )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages that aren't commands."""
    # Check if it's a command (starts with /)
    if update.message.text.startswith('/'):
        return
    
    # Generate image from text
    await generate_image(update, context)


def main() -> None:
    """Start the bot."""
    try:
        # Create Application
        application = Application.builder().token(TOKEN).build()
        
        # Add command handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("style", style_command))
        application.add_handler(CommandHandler("settings", settings_command))
        application.add_handler(CommandHandler("generate", generate_command))
        
        # Add callback handler for inline buttons
        application.add_handler(CallbackQueryHandler(button_callback))
        
        # Add message handler for text messages (not commands)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
        
        # Start the Bot
        logger.info("🚀 ImageGenie1Bot started successfully!")
        logger.info("🎨 Press Ctrl+C to stop.")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
