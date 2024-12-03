from pyrogram import Client, filters
from PyPDF2 import PdfReader, PdfWriter
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os
import tempfile
from pathlib import Path
import logging
import shutil
import re
import asyncio  # Import asyncio for handling locks
from flask import Flask
import threading
import requests

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Flask(__name__)

@bot.route('/')
def hello_world():
    return 'Hello, World!'

@bot.route('/health')
def health_check():
    return 'Healthy', 200

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
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id

    # Clear any previous files from the user's directory
    if user_dir.exists():
        shutil.rmtree(user_dir)  # Delete the entire directory
    user_dir.mkdir(exist_ok=True)  # Recreate the directory

    username = message.from_user.username
    await message.reply_photo(
        photo="https://raw.githubusercontent.com/darkhacker34/PDF-MERGER/refs/heads/main/MasterGreenLogo.jpg",
        caption=f"Hello @{username},\n\nSend me the PDF files, and I can merge or split them.\n\nUse /help for instructions!",
        reply_markup=InlineKeyboardMarkup([[ 
            InlineKeyboardButton("👤 OWNER", url="https://t.me/master_green_uae"),
            InlineKeyboardButton("🌐 WEBSITE", url="https://www.mastergreen.ae")
        ]])
    )

# Help message
HELP_MSG = """
Commands:

➡ /merge - Merge multiple PDFs (upload all PDFs first and send the command).

➡ /split (start-end) - Split a PDF by specifying the page range.

e.g., /split 1-3 (for pages 1 to 3) or /split 2-2 (for a single page).
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


@app.on_message(filters.document)
async def pdf_handler(client, message):
    if message.document.mime_type == "application/pdf":
        chat_id = str(message.chat.id)
        user_dir = temp_dir / chat_id
        user_dir.mkdir(exist_ok=True)

        async with file_download_lock:
            # Determine the next file name (1.pdf, 2.pdf, etc.)
            existing_files = list(user_dir.glob("*.pdf"))
            next_file_number = len(existing_files) + 1
            file_path = user_dir / f"{next_file_number}.pdf"

            # Save the name of the first PDF uploaded by the user (without the extension)
            if next_file_number == 1:
                user_states[chat_id] = {"first_pdf_base_name": os.path.splitext(message.document.file_name)[0]}
            else:
                user_states.setdefault(chat_id, {})  # Ensure user state exists for this chat

            # Delete the last download message if it exists
            last_msg_id = user_states[chat_id].get("last_download_msg_id")
            if last_msg_id:
                try:
                    await client.delete_messages(chat_id, last_msg_id)
                except Exception as e:
                    logger.warning(f"Failed to delete last message for user {chat_id}: {e}")

            # Download and save the file with progress bar
            download_msg = await message.reply("Downloading...")
            try:
                await message.download(file_path, progress=progress, progress_args=(download_msg, message.document.file_name))
                
                # Get total page count
                reader = PdfReader(file_path)
                page_count = len(reader.pages)
                
                # Notify user with page count and instructions
                await download_msg.edit(
                    f"PDF file Saved as {file_path.name}\n\n"
                    f"Total Pages: {page_count}\n\n"
                    "Use /merge to combine files or /split - to split."
                )

                # Update the last download message ID in user states
                user_states[chat_id]["last_download_msg_id"] = download_msg.id

            except Exception as e:
                logger.error(f"File download error: {e}")
                await download_msg.edit("An error occurred during the download. Please try again.")
    else:
        await message.reply("This file is not a PDF. Please upload a valid PDF file.")





@app.on_message(filters.command("merge"))
async def merge_handler(client, message):
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = sorted(user_dir.glob("*.pdf"))  # Ensure sequential order

    if len(pdf_files) < 2:
        await message.reply("Please Upload at Least Two PDFs to Merge.")
        return

    # Use the base name of the first PDF uploaded, excluding the extension
    first_pdf_base_name = user_states[chat_id]["first_pdf_base_name"]
    output_path = user_dir / f"{first_pdf_base_name}.pdf"

    try:
        merge_pdfs(pdf_files, output_path)
        await send_file_to_user(chat_id, message, output_path)
    except Exception as e:
        await message.reply(f"Error during merging: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files

@app.on_message(filters.command("split"))
async def split_handler(client, message):
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = list(user_dir.glob("*.pdf"))

    if len(pdf_files) != 1:
        await message.reply("Please upload a single PDF file to split.")
        return

    # Extract arguments from the command
    args = message.text.split()
    if len(args) != 2:
        await message.reply("Invalid command format! Use /split <start>-<end> or /split <page> (e.g., /split 1-3 or /split 5).")
        return

    try:
        input_file = pdf_files[0]
        reader = PdfReader(input_file)
        total_pages = len(reader.pages)

        # Determine the split range
        if "-" in args[1]:
            # Handle range format (e.g., 1-4)
            start, end = map(int, args[1].split("-"))
            if start < 1 or end > total_pages or start > end:
                await message.reply(f"Invalid page range! Please choose between 1 and {total_pages}.")
                return
            page_numbers = range(start, end + 1)
        else:
            # Handle single page format (e.g., 5)
            page_number = int(args[1])
            if page_number < 1 or page_number > total_pages:
                await message.reply(f"Invalid page number! Please choose between 1 and {total_pages}.")
                return
            page_numbers = [page_number]

        # Split the specified pages into a new PDF
        first_pdf_base_name = user_states[chat_id]["first_pdf_base_name"]
        output_path = user_dir / f"{first_pdf_base_name}.pdf"

        split_pdf(input_file, output_path, page_numbers)
        await send_file_to_user(chat_id, message, output_path)
    except Exception as e:
        logger.error(f"Error splitting the PDF: {e}")
        await message.reply(f"Error splitting the PDF: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files


# Helper function to send a file to the user
async def send_file_to_user(chat_id, message, file_path):
    thump = "https://raw.githubusercontent.com/darkhacker34/PDF-MERGER/refs/heads/main/MasterGreenLogo.jpg"

    # Path to save the downloaded thumbnail
    thumb_path = temp_dir / "thumbnail.jpg"
    if not thumb_path.exists():
        download_thumbnail(thump, thumb_path)

    # Send the file to the user with a progress bar
    upload_msg = await message.reply("Uploading Your File, Please Wait...")
    await message.reply_document(file_path, progress=progress, thumb=str(thumb_path), progress_args=(upload_msg, file_path.name))
    await upload_msg.edit(f"Here Is Your File: {file_path.name}")

    # Clean up user files after sending the file
    user_dir = temp_dir / chat_id
    shutil.rmtree(user_dir, ignore_errors=True)  # Remove all files for the user
    user_states.pop(chat_id, None)  # Clear state

# Start the Flask server in a separate thread
if __name__ == '__main__':
    threading.Thread(target=run_flask).start()

    # Start the Pyrogram Client
    app.run()
