
from datetime import datetime
from pathlib import Path
import os

LOG_FILE = Path("log.txt")
TMP_LOG = Path('log.txt.tmp')
MAX_LOGS = 5
LogLevel = 1



def item(msg, level = 1):
    os.chdir("/home/pi")
    if level <= LogLevel:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}]({level}) {msg}\n")

def rotate_logs():
    global LOG_FILE, TMP_LOG, LogLevel
    os.chdir('/home/pi')
    if LOG_FILE.exists():
        LOG_FILE.rename("log.txt.tmp")

    item("Rotate logs")
    # Remove oldest

    oldest = Path(f"{LOG_FILE}.{MAX_LOGS}")
    if oldest.exists():
        item(f"Discard: {oldest}")
        oldest.unlink()

    # Shift existing logs up
    for i in range(MAX_LOGS - 1, 0, -1):
        item(f"Rotating log file: {LOG_FILE}.{i}")
        src = Path(f"log.txt.{i}")
        dst = Path(f"log.txt.{i + 1}")
        if src.exists():
            #print(f"Found old log file: {src}")
            #src.unlink()
            src.rename(dst)

    # Rotate current log

    if TMP_LOG.exists():
        item(f"Rotate previous log: {LOG_FILE}")
        TMP_LOG.rename("log.txt.1")
    else:
        item("No previous log")

    # initialize log level
    if os.path.exists("/home/pi/log2"):
        LogLevel = 2
    if os.path.exists("/home/pi/log3"):
        LogLevel = 3
    item(f"Kiosk starting with loglevel {LogLevel}")

