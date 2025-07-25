from flask import Flask
from server import app
import server
from gunicorn.app.base import BaseApplication
import os
import dotenv
import threading
import time
import domains
from alerts import startTGBot, stopTGBot


class GunicornApp(BaseApplication):
    def __init__(self, app, options=None):
        self.options = options or {}
        self.application = app
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None: # type: ignore
                self.cfg.set(key.lower(), value) # type: ignore

    def load(self):
        return self.application

def run_expiry_checker():
    """
    Background function to run notify_expiries every 2 minutes.
    """
    while True:
        try:
            print("Running expiry check...")
            domains.notify_expiries()
            print("Expiry check completed.")
        except Exception as e:
            print(f"Error in expiry checker: {e}")
        
        # Wait 2 minutes (120 seconds)
        time.sleep(120)

def post_worker_init(worker):
    """
    Called just after a worker has been forked.
    Start the Telegram bot in each worker process.
    """
    print(f"Starting Telegram bot in worker {worker.pid}")
    startTGBot(mainThread=True)
    
    # Register cleanup function for this worker
    import atexit
    atexit.register(stopTGBot)


if __name__ == '__main__':
    dotenv.load_dotenv()
    
    # Start the background expiry checker
    expiry_thread = threading.Thread(target=run_expiry_checker, daemon=True)
    expiry_thread.start()
    print("Started background expiry checker thread")
    
    # Don't start the Telegram bot here - it will be started in worker processes
    
    workers = os.getenv('WORKERS', 1)
    threads = os.getenv('THREADS', 2)
    workers = int(workers)
    threads = int(threads)

    options = {
        'bind': '0.0.0.0:5000',
        'workers': workers,
        'threads': threads,
        'post_worker_init': post_worker_init,
    }

    gunicorn_app = GunicornApp(server.app, options)
    print(f'Starting server with {workers} workers and {threads} threads', flush=True)
    gunicorn_app.run()
