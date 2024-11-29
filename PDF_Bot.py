import logging
import os
import shutil
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from PyPDF2 import PdfMerger, PdfReader
from pathlib import Path

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

@app.on_message(filters.private & filters.document)
def handle_pdf(client, message):
    if message.document.mime_type == "application/pdf":
        user_id = str(message.from_user.id)
        user_folder = create_user_folder(user_id)

        # Count existing PDFs to determine the new file name
        pdf_count = len([f for f in user_folder.iterdir() if f.suffix == ".pdf"]) + 1
        file_name = f"{pdf_count}.pdf"
        file_path = user_folder / file_name

        try:
            # Download and save the file
            message.download(file_path)
            message.reply(
                f"PDF saved as {file_name}. Send another PDF or click Merge to combine them.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Merge PDFs", callback_data="merge")]
                ])
            )
        except Exception as e:
            message.reply(f"Failed to download the file: {str(e)}")
            logger.error(f"Failed to download file {file_name}: {e}")
    else:
        message.reply("Please send a valid PDF file.")

@app.on_callback_query(filters.regex("merge"))
def merge_pdfs(client, callback_query):
    user_id = str(callback_query.from_user.id)
    user_folder = BASE_DIR / user_id
    output_pdf = user_folder / "merged.pdf"

    if not user_folder.exists() or len(list(user_folder.glob("*.pdf"))) < 2:
        callback_query.message.reply("You need to upload at least two PDFs to merge.")
        return

    merger = PdfMerger()

    try:
        pdf_files = sorted(user_folder.glob("*.pdf"), key=lambda f: int(f.stem))  # Sorting PDFs by filename
        
        for file_path in pdf_files:
            try:
                # Check for validity before adding to merger
                PdfReader(str(file_path))  # Check if it's a valid PDF
                merger.append(str(file_path))
            except Exception as e:
                callback_query.message.reply(f"Skipped {file_path.name}: {str(e)}")
                logger.warning(f"Failed to add {file_path.name} to merger: {e}")

        # Write the merged PDF to output
        merger.write(str(output_pdf))
        merger.close()

        # Send the merged PDF back to the user
        callback_query.message.reply_document(
            document=str(output_pdf), caption="Here is your merged PDF!"
        )
    except Exception as e:
        callback_query.message.reply(f"An error occurred: {str(e)}")
        logger.error(f"Error during PDF merge: {e}")
    finally:
        # Clean up the user's folder after the merge
        clean_user_folder(user_folder)

if __name__ == "__main__":
    if not BASE_DIR.exists():
        BASE_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Bot is running...")
    app.run()
