

from pyrogram import Client, filters
from PyPDF2 import PdfReader, PdfWriter
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
import os
import tempfile
from pathlib import Path
import logging
import shutil
import re
import asyncio  # Import asyncio for handling locks
from flask import Flask, jsonify, send_file
import threading
import requests


# Logging setup
temp_dir = Path(tempfile.gettempdir())
log_file_path = temp_dir / "bot_logs.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file_path),
        logging.StreamHandler()  # Logs also appear on the console
    ]
)
logger = logging.getLogger(__name__)

bot = Flask(__name__)

@bot.route('/')
def hello_world():
    return 'Hello, World!'

@bot.route('/health')
def health_check():
    return 'Healthy', 200

# Endpoint to monitor bot activity
@bot.route('/bot_activity')
def bot_activity():
    activity = {
        "active_users": len(user_states),
        "user_states": user_states
    }
    return jsonify(activity)

# Endpoint to fetch logs
@bot.route('/logs')
def fetch_logs():
    if log_file_path.exists():
        return send_file(log_file_path, as_attachment=True)
    else:
        return "Log file not found.", 404

def run_flask():
    bot.run(host='0.0.0.0', port=8000)

# Load environment variables
API_ID = os.getenv("TELEGRAM_API_ID", "1917094")
API_HASH = os.getenv("TELEGRAM_API_HASH", "43dbeb43f27f99752b44db7493bf38ad")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "6941473830:AAFnSuGhyDAU1LuOoBHQGBpeE1Im28-pV8k")

# Initialize the bot
app = Client("pdf_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary directory for user files
temp_dir = Path(tempfile.gettempdir())

# State tracking for user operations
user_states = {}

# Helper function to merge PDFs using PyPDF2
def merge_pdfs(pdf_list, output_path):
    try:
        writer = PdfWriter()
        for pdf_path in pdf_list:
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                writer.add_page(page)
        with open(output_path, "wb") as output_pdf:
            writer.write(output_pdf)
    except Exception as e:
        logger.error(f"Error merging PDFs: {e}")
        raise e

# Helper function to split a PDF
def split_pdf(input_file, output_file, page_numbers):
    try:
        reader = PdfReader(input_file)
        writer = PdfWriter()
        for page in page_numbers:
            if page - 1 < len(reader.pages):
                writer.add_page(reader.pages[page - 1])
        with open(output_file, "wb") as out_pdf:
            writer.write(out_pdf)
    except Exception as e:
        logger.error(f"Error splitting PDF: {e}")
        raise e

# Function to download thumbnail
def download_thumbnail(url, save_path):
    try:
        response = requests.get(url)
        response.raise_for_status()
        with open(save_path, "wb") as file:
            file.write(response.content)
        return save_path
    except Exception as e:
        logger.error(f"Failed to download thumbnail: {e}")
        return None

@app.on_message(filters.command("start"))
async def start_handler(client, message):

    username = message.from_user.username
    await message.reply_photo(
        photo="https://raw.githubusercontent.com/darkhacker34/PDF-MERGER/refs/heads/main/MasterGreenLogo.jpg",
        caption=f"Hello @{username},\n\nSend me the PDF files, and I can merge or split them.\n\nUse /help for instructions!",
        reply_markup=InlineKeyboardMarkup([[ 
            InlineKeyboardButton("👤 OWNER", url="https://t.me/master_green_uae"),
            InlineKeyboardButton("🌐 WEBSITE", url="https://www.mastergreen.ae")
        ]])
    )


@app.on_message(filters.command("clear"))
async def clear_handler(client, message):
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id

    # Check if the user's directory exists
    if user_dir.exists() and any(user_dir.iterdir()):  # Check if directory is not empty
        shutil.rmtree(user_dir)  # Delete the entire directory
        user_dir.mkdir(exist_ok=True)  # Recreate the directory
        await message.reply("All Files Cleared!")
    else:
        await message.reply("No files to clear")
# Help message
HELP_MSG = """
👋 **Welcome to PDF Bot!**

I can help you with managing your PDF files. Here’s how to use me:

**How it works:**
1. Upload one or more PDF files.
2. I’ll show you options to **Merge** or **Split** your PDFs using buttons.

**Features:**
➡ **Merge PDFs**:
   - Upload multiple PDF files.
   - Select "Merge" to combine them into a single PDF.

➡ **Split PDF**:
   - Upload a single PDF file.
   - Select "Split" and provide the page range or a single page number (e.g., `1-3` or `5`).

**Additional Commands:**
➡ `/clear` - Delete all temporary files and reset your session.

Need assistance? Feel free to ask! 😊
"""


# Handle "/help" command
@app.on_message(filters.command("help"))
async def help_handler(client, message):
    await message.reply(HELP_MSG)

# Helper function to display progress in Telegram with 10 graphical blocks
async def progress(current, total, message, file_name):
    progress_percent = (current / total) * 100
    progress_blocks = int(progress_percent // 10)  # 10 blocks for a 100% bar

    # Graphical progress bar with 10 blocks
    progress_bar = "🟩" * progress_blocks + "⬜" * (10 - progress_blocks)
    
    # Textual representation with graphical blocks
    progress_text = f"<b>In Process ⏳: {file_name}</b>\n\n[{progress_bar}] <i>{progress_percent:.1f}%</i>"
    
    # Update the message with the new progress bar
    await message.edit(progress_text)


# Lock to prevent simultaneous access
file_download_lock = asyncio.Lock()

# State tracking for user operations, including bot messages
user_states = {}

# Track bot messages for each user
async def track_bot_message(chat_id, message_id):
    if chat_id not in user_states:
        user_states[chat_id] = {"messages_to_delete": []}
    user_states[chat_id]["messages_to_delete"].append(message_id)


@app.on_callback_query(filters.regex(r"merge"))
async def merge_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = sorted(user_dir.glob("*.pdf"))  # Ensure sequential order

    if len(pdf_files) < 2:
        await callback_query.message.edit_text("Please Upload at Least Two PDFs to Merge.")
        return

    # Use the base name of the first PDF uploaded, excluding the extension
    first_pdf_base_name = user_states[chat_id]["first_pdf_base_name"]
    output_path = user_dir / f"{first_pdf_base_name}.pdf"

    try:
        merge_pdfs(pdf_files, output_path)
        await send_file_to_user(chat_id, callback_query.message, output_path)
    except Exception as e:
        await callback_query.message.edit_text(f"Error during merging: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files

@app.on_callback_query(filters.regex(r"split"))
async def split_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = list(user_dir.glob("*.pdf"))

    if len(pdf_files) != 1:
        await callback_query.message.edit_text("Please upload a single PDF file to split.")
        return

    try:
        input_file = pdf_files[0]
        reader = PdfReader(input_file)

        total_pages = len(reader.pages)
        logger.info(f"Total pages in the PDF: {total_pages} for chat_id: {chat_id}")

        # Prompt the user for page range
        await callback_query.message.edit_text(
            f"Please provide the page range or a single page number to split (e.g., `1-3` or `5`).\n"
            f"Total Pages: {total_pages}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Cancel", callback_data="cancel")]]
            ),
        )
        user_states[chat_id]["action"] = "split"
        user_states[chat_id]["total_pages"] = total_pages

    except Exception as e:
        logger.error(f"Error preparing for split operation: {e}")
        await callback_query.message.edit_text(f"Error preparing to split the PDF: {e}")
        return


@app.on_message(filters.text)
async def handle_split_range(client, message):
    chat_id = str(message.chat.id)
    state = user_states.get(chat_id, {})
    if state.get("action") != "split":
        return  # Ignore messages unrelated to split actions

    try:
        user_dir = temp_dir / chat_id
        pdf_files = list(user_dir.glob("*.pdf"))
        input_file = pdf_files[0]
        total_pages = state.get("total_pages")

        # Parse the user's page range input
        if "-" in message.text:
            start, end = map(int, message.text.split("-"))
            if start < 1 or end > total_pages or start > end:
                raise ValueError(f"Invalid page range! Must be between 1 and {total_pages}.")
            page_numbers = range(start, end + 1)
        else:
            page_number = int(message.text)
            if page_number < 1 or page_number > total_pages:
                raise ValueError(f"Invalid page number! Must be between 1 and {total_pages}.")
            page_numbers = [page_number]

        # Split the PDF
        first_pdf_base_name = state.get("first_pdf_base_name", "split_output")
        output_path = user_dir / f"{first_pdf_base_name}.pdf"
        split_pdf(input_file, output_path, page_numbers)

        # Send the resulting file to the user
        await send_file_to_user(chat_id, message, output_path)
        user_states.pop(chat_id, None)  # Reset state after successful split

    except ValueError as ve:
        logger.warning(f"User input error: {ve}")
        await message.reply(str(ve))
    except Exception as e:
        logger.error(f"Error splitting the PDF for chat_id {chat_id}: {e}")
        await message.reply(f"Error splitting the PDF: {e}")
        user_states.pop(chat_id, None)  # Clean up state on error


@app.on_message(filters.document)
async def pdf_handler(client, message):
    if message.document.mime_type == "application/pdf":
        chat_id = str(message.chat.id)
        user_dir = temp_dir / chat_id
        user_dir.mkdir(exist_ok=True)

        async with file_download_lock:
            # Get the original file name from the message
            original_file_name = message.document.file_name
            if not original_file_name:
                original_file_name = "unknown.pdf"

            # Ensure the file name is unique in the user's directory
            base_name, ext = os.path.splitext(original_file_name)
            unique_file_name = original_file_name
            counter = 1
            while (user_dir / unique_file_name).exists():
                unique_file_name = f"{base_name}_{counter}{ext}"
                counter += 1

            file_path = user_dir / unique_file_name

            # Save the name of the first PDF uploaded by the user (without the extension)
            if "first_pdf_base_name" not in user_states.get(chat_id, {}):
                user_states[chat_id] = {"first_pdf_base_name": base_name, "messages_to_delete": []}

            # Download and save the file with progress bar
            download_msg = await message.reply("Downloading...")
            await track_bot_message(chat_id, download_msg.id)  # Track this message for deletion
            try:
                await message.download(file_path, progress=progress, progress_args=(download_msg, original_file_name))

                # Get total page count of the uploaded PDF
                reader = PdfReader(file_path)
                page_count = len(reader.pages)

                # Count the total number of PDFs in the user's directory
                pdf_count = len(list(user_dir.glob("*.pdf")))

                # Notify user with the PDF details, page count, and the updated PDF count
                buttons = InlineKeyboardMarkup(
                    [[
                        InlineKeyboardButton("🪢 Merge", callback_data="merge"),
                        InlineKeyboardButton("✂️ Split", callback_data="split")
                    ]]
                )
                notify_msg = await download_msg.edit(
                    f"{pdf_count} PDF Added!\n\nPDF Name: {unique_file_name}\n\n"
                    f"Total Pages: {page_count}\n\n"
                    "Choose an action below:",
                    reply_markup=buttons
                )
                await track_bot_message(chat_id, notify_msg.id)  # Track this message for deletion
                user_states[chat_id]["last_download_msg_id"] = notify_msg.id

            except Exception as e:
                logger.error(f"File download error: {e}")
                await download_msg.edit("An error occurred during the download. Please try again.")
    else:
        reply_msg = await message.reply("This file is not a PDF. Please upload a valid PDF file.")
        await track_bot_message(str(message.chat.id), reply_msg.id)



async def send_file_to_user(chat_id, message, file_path):
    thump = "https://raw.githubusercontent.com/darkhacker34/PDF-MERGER/refs/heads/main/MasterGreenLogo.jpg"

    # Path to save the downloaded thumbnail
    thumb_path = temp_dir / "thumbnail.jpg"
    if not thumb_path.exists():
        download_thumbnail(thump, thumb_path)

    # Send the file to the user with a progress bar
    upload_msg = await message.reply("Uploading Your File, Please Wait...")
    await track_bot_message(chat_id, upload_msg.id)  # Track this message for deletion

    try:
        # Send the output file to the user
        doc_message = await message.reply_document(
            file_path,
            progress=progress,
            thumb=str(thumb_path),
            progress_args=(upload_msg, file_path.name),
        )

        # Notify user after sending the file
        await upload_msg.edit(f"Here is your file: {file_path.name}")

    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await upload_msg.edit("Failed to send the file. Please try again later.")
        return

    # Delete all bot-generated messages except the output file
    try:
        messages_to_delete = user_states[chat_id].get("messages_to_delete", [])
        if upload_msg.id in messages_to_delete:
            messages_to_delete.remove(upload_msg.id)  # Ensure the output notification isn't deleted
        await message._client.delete_messages(chat_id, messages_to_delete)
    except Exception as e:
        logger.error(f"Error deleting messages: {e}")

    # Clean up user files after sending the file
    user_dir = temp_dir / chat_id
    shutil.rmtree(user_dir, ignore_errors=True)  # Remove all temp files for the user
    user_states.pop(chat_id, None)  # Clear state




# Start the Flask server in a separate thread
if __name__ == '__main__':
    threading.Thread(target=run_flask).start()

    # Start the Pyrogram Client
    app.run()
