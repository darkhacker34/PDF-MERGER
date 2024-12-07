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
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Initialize the bot
app = Client("pdf_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary directory for user files
temp_dir = Path(tempfile.gettempdir())

# State tracking for user operations
user_states = {}

# Helper function to merge PDFs using PyPDF2
def merge_pdfs(pdf_list, output_path, chat_id):
    try:
        writer = PdfWriter()
        for pdf_path in pdf_list:
            # Check cancellation
            if user_states.get(chat_id, {}).get("cancel"):
                raise Exception("Operation canceled by the user.")
            reader = PdfReader(pdf_path)
            for page in reader.pages:
                writer.add_page(page)
        with open(output_path, "wb") as output_pdf:
            writer.write(output_pdf)
    except Exception as e:
        logger.error(f"Error merging PDFs: {e}")
        raise e


@app.on_callback_query(filters.regex(r"cancel"))
async def cancel_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)

    # Set the cancellation flag for the user
    if chat_id in user_states:
        user_states[chat_id]["cancel"] = True

    # Clean up temporary files
    user_dir = temp_dir / chat_id
    shutil.rmtree(user_dir, ignore_errors=True)

    # Reset user state
    user_states.pop(chat_id, None)

    # Notify the user
    await callback_query.message.edit_text("❌ Operation canceled. You can start a new task.")


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
        caption=f"Hello @{username},\n\n​🇸​​🇪​​🇳​​🇩​ ​🇾​​🇴​​🇺​​🇷​ ​🇲​​🇬​ ​🇶​​🇺​​🇴​​🇹​​🇦​​🇹​​🇮​​🇴​​🇳​\n\nUse /help For Instructions!",
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
# Example: Check cancellation in a loop
async def progress(current, total, message, file_name):
    chat_id = str(message.chat.id)
    
    # Check if the user has canceled the process
    if user_states.get(chat_id, {}).get("cancel"):
        raise asyncio.CancelledError("Operation canceled by the user.")  # Raise cancellation error
    
    progress_percent = (current / total) * 100
    progress_blocks = int(progress_percent // 10)  # 10 blocks for a 100% bar
    progress_bar = "🟦" * progress_blocks + "⬜" * (10 - progress_blocks)
    progress_text = f"<b>In Process ⏳: {file_name}</b>\n\n[{progress_bar}] <i>{progress_percent:.1f}%</i>"
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


@app.on_callback_query(filters.regex(r"mg"))
async def merge_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = sorted(user_dir.glob("*.pdf"))  # Ensure sequential order

    if len(pdf_files) < 2:  # Check if at least two PDFs are uploaded
        await callback_query.answer(  # Send a popup message
            "Please Upload at Least Two PDFs to Merge.", 
            show_alert=True  # Set to True to display as a popup
        )
        return

    # Use the base name of the first PDF uploaded, excluding the extension
    first_pdf_base_name = user_states[chat_id]["first_pdf_base_name"]
    output_path = user_dir / f"{first_pdf_base_name}.pdf"

    try:
        merge_pdfs(pdf_files, output_path, chat_id)  # Pass pdf_list, output_path, and chat_id
        await send_file_to_user(chat_id, callback_query.message, output_path)
    except Exception as e:
        await callback_query.message.edit_text(f"Error during merging: {e}")
        shutil.rmtree(user_dir, ignore_errors=True)  # Clean up user files



@app.on_callback_query(filters.regex(r"splt"))
async def split_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = list(user_dir.glob("*.pdf"))

    if len(pdf_files) != 1:  # Ensure only one PDF is uploaded
        await callback_query.answer(  # Send a popup message
            "Please upload a single PDF file to split.", 
            show_alert=True  # Set to True to display the message as a popup
        )
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
                [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
            ),
        )
        user_states[chat_id]["action"] = "splt"
        user_states[chat_id]["total_pages"] = total_pages

    except Exception as e:
        logger.error(f"Error preparing for split operation: {e}")
        await callback_query.message.edit_text(f"Error preparing to split the PDF: {e}")
        return


@app.on_message(filters.text & filters.private)
async def handle_text_messages(client, message):
    chat_id = str(message.chat.id)
    state = user_states.get(chat_id, {})
    current_action = state.get("action")


    # Handle Rename Action
    if current_action == "rename":
        new_name = message.text.strip()  # Get the new name
        if not new_name:  # Validate the name
            invalid_msg = await message.reply("Invalid name. Please try again.")
            user_states[chat_id].setdefault("messages_to_delete", []).append(invalid_msg.id)
            return

        # Get the uploaded PDF path and directory
        pdf_path = user_states[chat_id].get("uploaded_pdf_path")
        if not pdf_path:
            error_msg = await message.reply("No PDF found for renaming. Please upload a file first.")
            user_states[chat_id].setdefault("messages_to_delete", []).append(error_msg.id)
            return

        user_dir = temp_dir / chat_id
        new_pdf_path = user_dir / f"{new_name}.pdf"

        try:
            # Rename the file with progress
            reader = PdfReader(pdf_path)
            writer = PdfWriter()
            total_pages = len(reader.pages)  # Get total number of pages
            rename_msg = await message.reply("Renaming the file...")  # Initial progress message
            user_states[chat_id].setdefault("messages_to_delete", []).append(rename_msg.id)

            # Add pages to the new PDF with progress updates
            for current_page, page in enumerate(reader.pages, start=1):
                writer.add_page(page)

                # Update progress after each page
                await progress(current_page, total_pages, rename_msg, new_name)

            # Save the renamed file
            with open(new_pdf_path, "wb") as new_pdf_file:
                writer.write(new_pdf_file)

            # Notify the user and send the renamed file
            completion_msg = await rename_msg.edit("Renaming complete. Uploading the file...")
            user_states[chat_id]["messages_to_delete"].append(completion_msg.id)

            sent_file_msg = await message.reply_document(
                document=new_pdf_path,
                caption=f"Here is your renamed PDF: `{new_name}.pdf`"
            )

        except Exception as e:
            error_msg = await message.reply(f"An error occurred while renaming: {e}")
            user_states[chat_id].setdefault("messages_to_delete", []).append(error_msg.id)
            logger.error(f"Error renaming PDF for chat_id {chat_id}: {e}")
        finally:
            # Clean up temporary files
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if os.path.exists(new_pdf_path):
                os.remove(new_pdf_path)

            # Remove user directory if empty
            if user_dir.exists() and not any(user_dir.iterdir()):
                shutil.rmtree(user_dir)

            # Delete bot-generated messages
            try:
                messages_to_delete = user_states[chat_id].get("messages_to_delete", [])
                await client.delete_messages(chat_id, messages_to_delete)
            except Exception as e:
                logger.error(f"Error deleting messages for chat_id {chat_id}: {e}")

            # Clear user state
            user_states.pop(chat_id, None)
            return
        await message.reply("I didn't understand that. Please use /help for instructions.")
        return


    elif current_action == "splt":
        user_dir = temp_dir / chat_id
        pdf_files = list(user_dir.glob("*.pdf"))
        input_file = pdf_files[0]  # Assume there's only one PDF file for splitting
        total_pages = state.get("total_pages")

        try:
            # Parse user input for page range
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
            original_file_name = input_file.stem  # Get the base name of the file (without extension)
            output_path = user_dir / f"{original_file_name}.pdf"
            split_pdf(input_file, output_path, page_numbers)

            # Send the split file to the user
            await send_file_to_user(chat_id, message, output_path)
            user_states.pop(chat_id, None)  # Reset state after successful split

        except ValueError as ve:
            logger.warning(f"User input error: {ve}")
            await message.reply(str(ve))
        except Exception as e:
            logger.error(f"Error splitting the PDF for chat_id {chat_id}: {e}")
            await message.reply(f"Error splitting the PDF: {e}")
            user_states.pop(chat_id, None)  # Clean up state on error
        return

    # Default response for other text inputs
    await message.reply("I didn't understand that. Please use /help for instructions.")





@app.on_callback_query(filters.regex(r"cancel"))
async def cancel_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)

    # Set the cancellation flag for the user
    if chat_id in user_states:
        user_states[chat_id]["cancel"] = True

    # Clean up temporary files
    user_dir = temp_dir / chat_id
    shutil.rmtree(user_dir, ignore_errors=True)

    # Reset user state
    user_states.pop(chat_id, None)

    # Notify the user
    await callback_query.message.edit_text("❌ Operation canceled. You can start a new task.")



@app.on_message(filters.document)
async def pdf_handler(client, message):
    if message.document.mime_type == "application/pdf":
        chat_id = str(message.chat.id)
        user_dir = temp_dir / chat_id
        user_dir.mkdir(exist_ok=True)

        # Reset cancellation flag for the user
        if chat_id not in user_states:
            user_states[chat_id] = {}
        user_states[chat_id]["cancel"] = False  # Reset cancel flag

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
            if "first_pdf_base_name" not in user_states[chat_id]:
                user_states[chat_id]["first_pdf_base_name"] = base_name
                user_states[chat_id]["messages_to_delete"] = []

            # Download and save the file with a progress bar
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
    [
        [
            InlineKeyboardButton("🪢 Merge", callback_data="mg"),
            InlineKeyboardButton("✂️ Split", callback_data="splt"),
        ],
        [
            InlineKeyboardButton("📂 List Files", callback_data="list_files"),
            InlineKeyboardButton("📄 Rename", callback_data="rename"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ]
)

                
                notify_msg = await download_msg.edit(
                    f"{pdf_count} PDF Added!\n\nPDF Name: {unique_file_name}\n\n"
                    f"Total Pages: {page_count}\n\n"
                    "Choose an action below:",
                    reply_markup=buttons,
                )
                await track_bot_message(chat_id, notify_msg.id)  # Track this message for deletion
                user_states[chat_id]["last_download_msg_id"] = notify_msg.id

            except Exception as e:
                logger.error(f"File download error: {e}")
                await download_msg.edit("An error occurred during the download. Please try again.")
    else:
        reply_msg = await message.reply("This file is not a PDF. Please upload a valid PDF file.")
        await track_bot_message(str(message.chat.id), reply_msg.id)


@app.on_callback_query(filters.regex(r"rename"))
async def rename_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id
    pdf_files = list(user_dir.glob("*.pdf"))

    # Check if only one PDF is uploaded
    if len(pdf_files) != 1:
        await callback_query.answer("Send a single PDF, then click Rename.", show_alert=True)
        return

    # Prompt user for a new name
    nam = await callback_query.message.edit_text(
        "Send me the new name (without extension) for the PDF:",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Cancel", callback_data="cancel")]]
        ),
    )

    # Update user state
    user_states[chat_id]["action"] = "rename"
    user_states[chat_id]["uploaded_pdf_path"] = pdf_files[0]
    user_states[chat_id]["messages_to_delete"] = []


@app.on_callback_query(filters.regex(r"list_files"))
async def list_files_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id

    # Check if user directory exists
    if not user_dir.exists() or not any(user_dir.iterdir()):
        await callback_query.message.edit_text("📂 No files uploaded yet.", reply_markup=None)
        return

    # List files with delete buttons for each
    files = list(user_dir.glob("*.pdf"))
    file_buttons = [
        [
            InlineKeyboardButton(f"🗑️ Delete {file.name}", callback_data=f"delete_file:{file.name}")
        ]
        for file in files
    ]

    # Add "Back" button to return to the main menu
    file_buttons.append([InlineKeyboardButton("⬅ Back", callback_data="main_menu")])

    await callback_query.message.edit_text(
        "📂 **Uploaded Files:**\n\nSelect a file to delete:",
        reply_markup=InlineKeyboardMarkup(file_buttons),
    )


@app.on_callback_query(filters.regex(r"main_menu"))
async def main_menu_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    user_dir = temp_dir / chat_id

    # Count the total number of PDFs in the user's directory
    pdf_count = len(list(user_dir.glob("*.pdf")))

    # Notify user with the main menu options
    buttons = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton("🪢 Merge", callback_data="mg"),
            InlineKeyboardButton("✂️ Split", callback_data="splt"),
        ],
        [
            InlineKeyboardButton("📂 List Files", callback_data="list_files"),
            InlineKeyboardButton("📄 Rename", callback_data="rename"),
        ],
        [
            InlineKeyboardButton("❌ Cancel", callback_data="cancel"),
        ],
    ]
)


    await callback_query.message.edit_text(
        f"📂 **Main Menu:**\n\n"
        f"Uploaded PDFs: {pdf_count}\n\n"
        "Choose an action below:",
        reply_markup=buttons,
    )


@app.on_callback_query(filters.regex(r"delete_file:(.+)"))
async def delete_file_handler(client, callback_query: CallbackQuery):
    chat_id = str(callback_query.message.chat.id)
    file_name = callback_query.matches[0].group(1)
    user_dir = temp_dir / chat_id
    file_path = user_dir / file_name

    # Delete the selected file
    if file_path.exists():
        file_path.unlink()  # Remove the file
        await callback_query.answer(f"{file_name} deleted.", show_alert=True)

        # Refresh the file list
        files_remaining = list(user_dir.glob("*.pdf"))  # Check remaining files
        if len(files_remaining) > 0:  # If files still exist, refresh the list
            await list_files_handler(client, callback_query)
        else:  # If no files are left, return to the main menu
            await callback_query.message.edit_text(
                "📂 No files uploaded yet.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅ Back", callback_data="main_menu")]]
                )
            )
    else:
        await callback_query.answer("File not found!", show_alert=True)




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
