from flask import Flask
import threading
import subprocess
import time
import requests

app = Flask(__name__)

@app.route("/")
def health_check():
    return "OK", 200  # Respond to health check pings

def keep_alive():
    """Pings the bot periodically to prevent the instance from sleeping."""
    while True:
        try:
            requests.get("http://127.0.0.1:8000")  # Ping itself
        except Exception as e:
            print(f"Ping failed: {e}")
        time.sleep(300)  # Ping every 5 minutes

def start_bot():
    """Runs the bot and restarts if it crashes."""
    while True:
        print("Starting the bot...")
        try:
            process = subprocess.Popen(["python", "PDF_Bot.py"])
            process.wait()
        except Exception as e:
            print(f"Bot crashed: {e}")

        print("Restarting bot in 5 seconds...")
        time.sleep(5)

if __name__ == "__main__":
    # Run bot in a separate thread
    bot_thread = threading.Thread(target=start_bot, daemon=True)
    bot_thread.start()

    # Run keep-alive function in a separate thread
    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()

    # Start Flask server
    app.run(host="0.0.0.0", port=8000)
