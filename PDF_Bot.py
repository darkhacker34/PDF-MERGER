import logging
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from pyrogram.handlers import MessageHandler
from PyPDF2 import PdfMerger, PdfReader
from pathlib import Path
import asyncio
import time

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize the bot
API_ID = "1917094"
API_HASH = "43dbeb43f27f99752b44db7493bf38ad"
BOT_TOKEN = "6941473830:AAHrNNHnu8jaHdbMR_JSTwjncASwNF7OQIA"

app = Client("pdf_merge_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Temporary storage for user files
BASE_DIR = Path("user_files")

def create_user_folder(user_id: str) -> Path:
    """Create a user folder if it doesn't exist."""
    user_folder = BASE_DIR / str(user_id)
    user_folder.mkdir(parents=True, exist_ok=True)
    return user_folder

def clean_user_folder(user_folder: Path):
    """Remove the user's folder and its contents."""
    try:
        shutil.rmtree(user_folder)
    except Exception as e:
        logger.error(f"Failed to clean user folder {user_folder}: {e}")

@app.on_message(filters.command('start'))
async def start(bot, msg):
    """Handle the '/start' command."""
    username = msg.from_user.username
    await msg.reply_photo(
        photo="https://raw.githubusercontent.com/darkhacker34/PDF-MERGER/main/MasterGreenLogo.jpg",
        caption=f"𝙷𝚢  @{username}🤫..!!\n𝚆𝚎𝚕𝚌𝚘𝚖𝚎 𝚃𝚘 Master Green Bot.!\n\n𝗠𝗲𝗿𝗴𝗲 𝗬𝗼𝘂𝗿 𝗠𝗚 𝗤𝘂𝗼𝘁𝗮𝘁𝗶𝗼𝗻",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👤 OWNER", url="https://t.me/master_green_uae")],
            [InlineKeyboardButton("🌐 WEBSITE", url="https://www.mastergreen.ae")]
        ])
    )

@app.on_message(filters.private & filters.document)
async def handle_pdf(client, message):
    """Handle PDF uploads from the user."""
    if message.document.mime_type == "application/pdf":
        user_id = str(message.from_user.id)
        user_folder = create_user_folder(user_id)

        # Count existing PDFs to determine the new file name
        pdf_count = len([f for f in user_folder.iterdir() if f.suffix == ".pdf"]) + 1
        file_name = f"{pdf_count}.pdf"
        file_path = user_folder / file_name

        try:
            # Download and save the file with progress updates
            await message.download(file_path)
            await message.reply(
                f"PDF saved as {file_name}. Send another PDF or click Merge to combine them.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Merge PDFs", callback_data="merge")]
                ])
            )
        except Exception as e:
            await message.reply(f"Failed to download the file: {str(e)}")
            logger.error(f"Failed to download file {file_name}: {e}")
    else:
        await message.reply("Please send a valid PDF file.")

@app.on_callback_query(filters.regex("merge"))
async def merge_pdfs(client, callback_query):
    """Merge all uploaded PDFs and send back to the user with progress updates."""
    user_id = str(callback_query.from_user.id)
    user_folder = BASE_DIR / user_id

    if not user_folder.exists() or len(list(user_folder.glob("*.pdf"))) < 2:
        await callback_query.message.reply("You need to upload at least two PDFs to merge.")
        return

    # Ask user for a new file name for the merged PDF
    await callback_query.message.reply(
        "Please enter a new name for the merged PDF (without extension).",
        reply_markup=ReplyKeyboardRemove()
    )
    app.add_handler(MessageHandler(handle_rename, filters.private))

async def handle_rename(client, message):
    """Handle the new name for the merged PDF."""
    user_id = str(message.from_user.id)
    user_folder = BASE_DIR / user_id
    new_pdf_name = message.text.strip()  # Get new file name from the user
    output_pdf = user_folder / f"{new_pdf_name}.pdf"

    if not new_pdf_name:
        await message.reply("The name cannot be empty. Please provide a valid name.")
        return

    # Acknowledge the user's input and start the merge process
    response_message = await message.reply("Merging PDFs... Please wait.")

    # Start the merge task in a separate thread
    await merge_pdfs_task(client, response_message, user_folder, output_pdf)

async def merge_pdfs_task(client, response_message, user_folder, output_pdf):
    """Handle PDF merging asynchronously with progress updates."""
    merger = PdfMerger()

    try:
        pdf_files = sorted(user_folder.glob("*.pdf"), key=lambda f: int(f.stem))  # Sorting PDFs by filename
        total_pdfs = len(pdf_files)
        current_pdf = 0
        progress_indicator = "○ ○ ○ ○ ○"  # Placeholder for progress

        # Update progress periodically, reduce the frequency of updates
        for file_path in pdf_files:
            try:
                # Check for validity before adding to merger
                PdfReader(str(file_path))  # Check if it's a valid PDF
                merger.append(str(file_path))
                current_pdf += 1

                # Update progress every 1 second or after each PDF processed
                progress_indicator = "●" * current_pdf + " ○" * (total_pdfs - current_pdf)
                await response_message.edit_text(
                    f"Processing PDF {current_pdf} of {total_pdfs}...\nProgress: {progress_indicator}"
                )
                await asyncio.sleep(1)  # Sleep to simulate progress and avoid overwhelming Telegram with too many updates

            except Exception as e:
                await response_message.reply(f"Skipped {file_path.name}: {str(e)}")
                logger.warning(f"Failed to add {file_path.name} to merger: {e}")

        # Write the merged PDF to output
        merger.write(str(output_pdf))
        merger.close()

        # Send the merged PDF back to the user
        await response_message.edit_text("Merging complete. Sending the merged file...")
        await response_message.reply_document(
            document=str(output_pdf), caption="Here is your merged PDF!"
        )
    except Exception as e:
        await response_message.reply(f"An error occurred: {str(e)}")
        logger.error(f"Error during PDF merge: {e}")
    finally:
        # Clean up the user's folder after the merge
        clean_user_folder(user_folder)

if __name__ == "__main__":
    if not BASE_DIR.exists():
        BASE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Bot is running...")
    app.run()
