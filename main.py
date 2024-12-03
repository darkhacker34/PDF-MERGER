import subprocess
import time

def start_bot():
    """
    Starts the bot as a subprocess and monitors its status.
    Restarts the bot if it exits unexpectedly.
    """
    while True:
        print("Starting the bot...")
        try:
            # Run the bot script
            process = subprocess.Popen(["python", "PDF_Bot.py"])
            process.wait()  # Wait for the bot process to exit
        except Exception as e:
            print(f"Error occurred while running the bot: {e}")
        
        # Log restart and wait before restarting
        print("Bot stopped unexpectedly. Restarting in 5 seconds...")
        time.sleep(5)  # Short delay before restarting the bot

if __name__ == "__main__":
    start_bot()
