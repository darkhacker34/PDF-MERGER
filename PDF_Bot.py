from pyrogram import Client, filters
from PyPDF2 import PdfReader, PdfWriter
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os
import tempfile
from pathlib import Path
import logging
import shutil
import re
from flask import Flask
import threading
import subprocess

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

# Helper function to validate PDF file names
def is_valid_pdf_name(file_name):
    return bool(re.match(r'^[\w,\s-]+\.[Pp][Dd][Ff]$', file_name))

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

# Handle "/start" command
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
    progress_text = f"<b>Downloading: {file_name}</b>\n\n[{progress_bar}] <i>{progress_percent:.1f}%</i>"
    
    # Update the message with the new progress bar
    await message.edit(progress_text)


# Handle PDF uploads
@app.on_message(filters.document)
async def pdf_handler(client, message):
    if message.document.mime_type == "application/pdf":
        chat_id = str(message.chat.id)
        user_dir = temp_dir / chat_id
        user_dir.mkdir(exist_ok=True)

        # Determine the next file name (1.pdf, 2.pdf, etc.)
        existing_files = list(user_dir.glob("*.pdf"))
        next_file_number = len(existing_files) + 1
        file_path = user_dir / f"{next_file_number}.pdf"

        # Download and save the file with progress bar
        download_msg = await message.reply("Starting to download your PDF...")
        await message.download(file_path, progress=progress, progress_args=(download_msg, message.document.file_name))
        await download_msg.edit(f"PDF file saved as {file_path.name}\n\nUse /merge to combine files or /split <start>-<end> to split.")
    else:
        await message.reply("This file is not a PDF. Please upload a valid PDF file.")

# Handle "/merge" command
@app.on_message(filters.command("merge"))
async def merge_handler(client, message):
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = sorted(user_dir.glob("*.pdf"))  # Ensure sequential order
    
    if len(pdf_files) < 2:
        await message.reply("Please upload at least two PDF files to merge.")
        return

    output_path = user_dir / "merged.pdf"
    try:
        merge_pdfs(pdf_files, output_path)
        await message.reply("Merging Complete!\n\nPlease Enter A New Name For The PDF With Extension. (eg:- MG_Quotation.pdf).")
        user_states[chat_id] = {"operation": "merge", "file_path": output_path}
    except Exception as e:
        await message.reply(f"Error during merging: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files

# Handle "/split" command
@app.on_message(filters.command("split"))
async def split_handler(client, message):
    chat_id = str(message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = list(user_dir.glob("*.pdf"))
    
    if len(pdf_files) != 1:
        await message.reply("Please upload a single PDF file to split.")
        return

    args = message.text.split()
    if len(args) != 2 or "-" not in args[1]:
        await message.reply("Invalid command format! Use /split <start>-<end> (e.g., /split 1-3).")
        return

    try:
        start, end = map(int, args[1].split("-"))
        output_path = user_dir / "split.pdf"
        split_pdf(pdf_files[0], output_path, range(start, end + 1))
        await message.reply("Splitting Complete!\n\nPlease Enter A New Name For The PDF With Extension. (eg:- MG_Quotation.pdf).")
        user_states[chat_id] = {"operation": "split", "file_path": output_path}
    except Exception as e:
        await message.reply(f"Error splitting the PDF: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files

# Handle user's reply for naming the file
@app.on_message(filters.text & filters.create(lambda _, __, msg: not msg.text.startswith("/")))
async def rename_output_handler(client, message):
    chat_id = str(message.chat.id)
    state = user_states.get(chat_id)

    if state:
        desired_name = message.text.strip()
        if not is_valid_pdf_name(desired_name):
            await message.reply("Invalid file name! Please ensure it ends with .pdf and contains no special characters.")
            return

        # Rename the file
        user_dir = temp_dir / chat_id
        new_path = user_dir / desired_name
        os.rename(state["file_path"], new_path)
        
        # Send the renamed file to the user with progress tracking
        upload_msg = await message.reply("Uploading your file, please wait...")
        await message.reply_document(new_path, progress=progress, progress_args=(upload_msg, desired_name))
        await upload_msg.edit(f"Here is your file: {desired_name}")
        
        # Clean up
        shutil.rmtree(user_dir, ignore_errors=True)  # Remove all files for the user
        user_states.pop(chat_id, None)  # Clear state
    else:
        await message.reply("""

ᴏʜ, ʀᴇᴀʟʟʏ? ᴛʜᴀᴛ’s ᴡʜᴀᴛ ʏᴏᴜ’ᴠᴇ ɢᴏᴛ ғᴏʀ ᴍᴇ? 🙄

ɪ’ᴍ ᴊᴜsᴛ ʜᴇʀᴇ ᴛᴏ ʜᴀɴᴅʟᴇ ᴘᴅғs, ɴᴏᴛ ʀᴇᴀᴅ ʏᴏᴜʀ ᴍɪɴᴅ!

ʜᴏᴡ ᴀʙᴏᴜᴛ ʏᴏᴜ sᴇɴᴅ ᴍᴇ ᴀ ᴘᴅғ ᴀɴᴅ ʟᴇᴛ ᴍᴇ ᴅᴏ ᴡʜᴀᴛ ɪ ᴅᴏ ʙᴇsᴛ—ʙᴇɪɴɢ ᴀ **ᴘᴅғ ᴡɪᴢᴀʀᴅ** 🧙‍♂️✨. ɪ ᴘʀᴏᴍɪsᴇ, ɴᴏ ᴍᴏʀᴇ sᴜʀᴘʀɪsᴇs!


""")

# Start the Flask server in a separate thread
if __name__ == '__main__':
    threading.Thread(target=run_flask).start()
    
    # Start the Pyrogram Client
    app.run()
