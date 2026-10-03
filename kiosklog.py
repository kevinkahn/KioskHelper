
from datetime import datetime
from pathlib import Path
import os

LOG_FILE = Path("log.txt")
MAX_LOGS = 5
LogLevel = 1



def item(msg, level = 1):
    os.chdir("/home/pi")
    if level <= LogLevel:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {msg}\n")

def rotate_logs():
    global LOG_FILE
    # Remove oldest
    os.chdir('/home/pi')
    oldest = Path(f"{LOG_FILE}.{MAX_LOGS}")
    if oldest.exists():
        print(f"Discard: {oldest}")
        oldest.unlink()

    # Shift existing logs up
    for i in range(MAX_LOGS - 1, 0, -1):
        print(f"Rotating log file: {LOG_FILE}.{i}")
        src = Path(f"log.txt.{i}")
        dst = Path(f"log.txt.{i + 1}")
        if src.exists():
            #print(f"Found old log file: {src}")
            #src.unlink()
            src.rename(dst)

    # Rotate current log
    if LOG_FILE.exists():
        print(f"Rotate previous log: {LOG_FILE}")
        LOG_FILE.rename("log.txt.1")

