import subprocess
import time
import signal
import sys

def handle_signal(sig, frame):
    """Handle termination signals gracefully."""
    print("Shutdown signal received. Exiting...")
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

def start_bot():
    """Starts the bot as a subprocess and restarts it if it crashes."""
    while True:
        print("Starting the bot...")
        try:
            process = subprocess.Popen(["python", "PDF_Bot.py"])
            process.wait()
        except Exception as e:
            print(f"Error occurred: {e}")

        print("Bot stopped. Restarting in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    start_bot()
