#/usr/bin/env python3

import subprocess
import threading
from random import randint

import panelbrightness as pb
import mqtthandling as mh
import kiosklog as log
import re
import parameters as p

from evdev import InputDevice, ecodes, categorize, UInput
import socket
import os, glob, time, sys
import signal
from pathlib import Path
from datetime import datetime, timedelta

def get_local_ip_gp():
    # return the local net number for choosing local HA
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
     # Does not have to be reachable to extract the local interface IP
       s.connect(('8.8.8.8', 1))
       ip = s.getsockname()[0]
    except Exception as e:
        log.item(f"Failed to get local ip address: {e}")
        ip = '127.0.0.1'
    finally:
        s.close()
    return int(ip.split('.')[2])

browser: subprocess.Popen | None = None
localnetcode = get_local_ip_gp()
browserrestarttimes = []
# Node name is pi dns name
nodename = os.uname().nodename
# Kiosk name is the name for the browser in HA
kioskname = f"kiosk_{nodename.replace('rpi-','')}"
kioskbaseurlentity = f"{kioskname}_baseurl"
log.item(f"Kiosk Info: node: {nodename} kioskname: {kioskname} kioskbaseurlentity: {kioskbaseurlentity} kiosk_baseurl: {p.kiosk_baseurl}", level=3)
locationgp = ('error', 'pdx', 'pgaw')[localnetcode] # user for group browser commands
HA_ID = ('error', 'HASS', 'HASSpga')[localnetcode]
log.item(f"Using local network: {localnetcode} Local group: {locationgp} HA Name: {HA_ID}")

resetcorner = ((0,0),(0,0))


def handle_sigterm(signum, frame):
    """Callback function triggered when SIGTERM is received."""
    log.item(f"Received SIGTERM (signal {signum}). Cleaning up resources...")
    try:
        if not browser is None:
            browser.terminate()
        log.item("Terminated browser")
    except Exception as e:
        log.item(f"Failed to terminate browser: {e}")
    sys.exit(0)
signal.signal(signal.SIGTERM, handle_sigterm)

def find_touchscreen_event():
    candidates = glob.glob("/dev/input/event*")

    for dev in candidates:
        name_path = f"/sys/class/input/{os.path.basename(dev)}/device/name"
        try:
            with open(name_path, "r") as devicesfile:
                name = devicesfile.read().strip().lower()

            # Heuristics for touchscreen devices
            if any(keyword in name for keyword in [
                "touch", "ft", "goodix", "hid", "panel", "display"
            ]):
                log.item(f"[touch] Using {dev} ({name})",level=2)
                return dev

        except Exception:
            continue

    log.item("[touch] No touchscreen found, falling back to event0")
    return "/dev/input/event0"

# ---------------------------
# Touch Listener
# ---------------------------
def GrabTouchScreen():
    global resetcorner
    log.item("Grabbing Touchscreen")
    event_dev = find_touchscreen_event()
    dev = InputDevice(event_dev)
    dev.grab()
    if os.path.exists("/home/pi/fliptouch"):
        log.item("Flip Touchscreen")
        ui = UInput.from_device(dev, name="Filtered Touchscreen Flipped")
        resetcorner = ((0,60),(420,480))
    else:
        log.item("Normal Touchscreen")
        ui = UInput.from_device(dev, name="Filtered Touchscreen")
        resetcorner = ((740, 800), (0, 60))
    return dev, ui

def touch_thread(dev, ui):
    log.item(f"Start Touch Thread {dev.name}, {ui.name}")
    swallow_gesture = 'no' # values are no, (timestamp of last), yes
    touch_active = False

    current_x = 0
    current_y = 0

    log.item(f"Listening for events on {dev.name}")

    start_x, start_y = 0, 0
    start_time = 0
    touch_down = False
    tap_count = 0
    last_tap_time = 0

    # Thresholds
    SWIPE_DIST = 100  # pixels
    TAP_MAX_TIME = 0.3  # seconds for a tap
    DOUBLE_TAP_WINDOW = 0.4  # seconds between taps

    for event in dev.read_loop():
        if event.type == ecodes.EV_ABS:
            absevent = categorize(event)
            log.item(f"absevent: {absevent}", level=3)
            if absevent.event.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                current_x = absevent.event.value
            elif absevent.event.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                current_y = absevent.event.value

        elif event.type == ecodes.EV_KEY and event.code == ecodes.BTN_TOUCH:
            if event.value == 1:  # Touch down
                touch_down = True
                touch_active = True
                if pb.bm.screenisdim:
                    log.item(f"Touch down screen brightness {pb.bm.screenisdim}", level=3)
                    pb.bm.wake_screen()
                    swallow_gesture = 'yes'
                    log.item(f"Swallow this gesture {categorize(event)}",level=3)
                start_x = current_x if 'current_x' in locals() else 0
                start_y = current_y if 'current_y' in locals() else 0
                start_time = time.time()
                log.item(f"Touch down: {start_x}, {start_y}", level=3)
            elif event.value == 0:  # Touch up
                touch_active = False
                if swallow_gesture == 'yes':
                    swallow_gesture = event.timestamp()
                    log.item(f"Ending swallow gesture {swallow_gesture}:{categorize(event)}",level=3)


                touch_down = False
                end_time = time.time()
                duration = end_time - start_time
                end_x = current_x if 'current_x' in locals() else start_x
                end_y = current_y if 'current_y' in locals() else start_y
                log.item(f"Touch up: {end_x}, {end_y} {'current_x' in locals()} {'current_y' in locals()}", level=3)

                dx = end_x - start_x
                dy = end_y - start_y
                dist = (dx ** 2 + dy ** 2) ** 0.5
                log.item(f"Touch pair dist: {dist} dx: {dx} dy: {dy} ")

                # Check for Swipe
                if dist > SWIPE_DIST:
                    if abs(dx) > abs(dy):
                        direction = "Right" if dx > 0 else "Left"
                    else:
                        direction = "Down" if dy > 0 else "Up"
                    log.item(f"Swipe detected: {direction}: {dx}, {dy}, {dist}")
                    log.item(f"Coords: {start_x} {end_x}, {start_y} {end_y}")
                    if direction in ("Down","Up"): mh.mq.sendbrowsercontrol("refresh")
                    if direction in ("Right","Left"): mh.mq.sendbrowsercontrol("maintenance")
                    tap_count = 0
                elif duration < TAP_MAX_TIME:
                    # Check for Taps
                    now = time.time()
                    if now - last_tap_time < DOUBLE_TAP_WINDOW:
                        tap_count += 1
                    else:
                        tap_count = 1
                    last_tap_time = now

                    if tap_count == 2:
                        log.item(f"Double tap detected at {current_x}, {current_y}", level=1)
                        if resetcorner[0][0] <= current_x <= resetcorner[0][1] and resetcorner[1][0] <= current_y <= resetcorner[1][1]:
                            log.item("Got a screen restart")
                            log.item("Kill existing browser")
                            p.browser.kill()
                            time.sleep(1)
                            start_browser(p.kiosk_baseurl, kioskname)
                        tap_count = 0
                    elif tap_count == 1:
                        log.item(f"Single tap detected at {current_x}, {current_y}", level=1)
        if swallow_gesture == 'no':
            log.item(f"Reflect event {categorize(event)}",level=3)
            ui.write_event(event)
        elif swallow_gesture == 'yes':
            log.item(f"Swallowed event {categorize(event)}",level=3)
        else:
            log.item(f"Swallowing last event(s) {swallow_gesture}:{categorize(event)}",level=3)
            if swallow_gesture != event.timestamp():
                log.item(f"Reflect post swallow event {swallow_gesture}:{categorize(event)}",level=3)
                ui.write_event(event)
                swallow_gesture = 'no'

            #if event.type == ecodes.EV_SYN:
            #    ui.syn()


def initialize_browser_environment(profile_dir, kiosknm):
    initurl = f"{p.HAIP}/lovelace/0?BrowserID={kiosknm}"
    log.item(f"[initialize_browser_environment] Initializing {initurl}" )
    initbrowser = subprocess.run([
        "/usr/lib/chromium/chromium",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--password-store=basic",
        f"--user-data-dir={profile_dir}"] + extrachromeflags +
        [initurl])
    log.item(f"Output: {initbrowser.stdout}")
    log.item(f"Errors: {initbrowser.stderr}")
    log.item(f"Exit Code: {initbrowser.returncode}")
    log.item("Finished first time run")

    # Remove lingering Chromium lock files before starting
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        file_path = os.path.join(profile_dir, lock_file)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def start_browser(burl, kiosknm):
    log.item(f"[start_browser] Starting {p.HAIP}" )
    url = f"{p.HAIP}{burl}"
    profile_dir = "/home/pi/.config/chromium-kioskscreen"
    profilepath = Path(profile_dir)
    if not profilepath.is_dir():
        initialize_browser_environment(profile_dir, kiosknm)

    log.item(f"[start_browser] Starting in {url}")
    p.browser = subprocess.Popen([
        "/usr/lib/chromium/chromium",
        "--kiosk",
        "--no-first-run",
        "--hide-scrollbars",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--password-store=basic",
        "--user-data-dir=/home/pi/.config/chromium-kioskscreen"] +
        extrachromeflags + [f"{url}?BrowserID={kiosknm}"] )
    log.item("Browser started")

def get_seconds_until_next(target_times):
    """Calculates exactly how many seconds to sleep until the next event."""
    now = datetime.now()
    seconds_distances = []

    for time_str in target_times:
        target_hour, target_minute = map(int, time_str.split(":"))
        target_dt = now.replace(
            hour=target_hour, minute=target_minute, second=0, microsecond=0
        )

        # If the time has already passed today, schedule it for tomorrow
        if target_dt <= now:
            target_dt += timedelta(days=1)

        seconds_distances.append((target_dt - now).total_seconds())

    return min(seconds_distances)

def periodic_browser_restart(timelist):
    log.item(f"Restart browser at {timelist}")
    while True:
        sleep_duration = (get_seconds_until_next(timelist))
        jitter = randint(0, 120)
        log.item(f"Sleeping efficiently for {sleep_duration} + {jitter} seconds")
        time.sleep(sleep_duration + jitter)
        log.item(f"Periodic browser restart at {datetime.now().strftime('%H:%M:%S')}")
        p.browser.kill()
        time.sleep(1)
        start_browser(p.kiosk_baseurl, kioskname)


if __name__ == "__main__":

    # Rotate logs
    log.rotate_logs()
    log.item(f"Kiosk starting with loglevel {log.LogLevel}")
    if os.path.exists("/home/pi/restarttimes.txt"):
        with open("/home/pi/restarttimes.txt", "r") as f:
            for line in f:
                clean_line = line.strip()
                # Skip empty lines or comment lines
                if not clean_line or clean_line.startswith("#"):
                    continue
                # Basic validation: ensure it follows the format HH:MM
                try:
                    datetime.strptime(clean_line, "%H:%M")
                    browserrestarttimes.append(clean_line)
                    log.item(f" -> Loaded target time: {clean_line}")
                except ValueError:
                    print(f" [Error] Skipping invalid format line: '{line.strip()}'")

    # Get restart times if set
    if not browserrestarttimes:
        log.item(f"No browser periodic restart")
    else:
        log.item(f"Browser restart times: {browserrestarttimes}")

    # Get pi information
    try:
        # Read the raw model name from the system's devicetree
        with open('/proc/device-tree/model', 'r') as f:
            raw_model = f.read().strip('\x00\n ')  # Strip null bytes and newlines

        # 1. Remove the "Raspberry Pi" text prefix
        model = raw_model.replace("Raspberry Pi", "").strip()

        # 2. Strip trailing hardware revisions (e.g., "Rev 1.2")
        model = re.sub(r'\s+Rev\s+\d+\.\d+', '', model, flags=re.IGNORECASE)
    except FileNotFoundError:
        model = 4
        log.item(f"Error getting model {raw_model}")
    log.item(f"Raspberry Pi model: {model}")
    if model == "3 Model B Plus":
        extrachromeflags = ["--disable-gpu", "--disable-software-rasterizer"]
        log.item(f"Suppress gpu: {extrachromeflags}")
    else:
        extrachromeflags = []

    # Lock the touchscreen to prevent browser from using it directly
    device, virtualtouch = GrabTouchScreen()

    # Set up mqtt and brightness managers
    mh.mq = mh.mqtt_handler(nodename, locationgp, HA_ID, kioskbaseurlentity)
    pb.bm = pb.BrightnessManager(15, mh.mq.sendbrowsercontrol)
    threading.Thread(target=mh.mq.mqtt_thread, daemon=True).start()
    log.item('Started MQTT handler')

    mh.mq.get_HAIP()

    if browserrestarttimes:
        log.item("Start Browser Restart Thread")
        threading.Thread(target=periodic_browser_restart, args=(browserrestarttimes,)).start()

    if p.kiosk_baseurl is None:
    # haven't set up this kiosk in HA yet else retained MQTT message would have set this
        log.item('Initializing kiosk in HA')
        discovery_payload = {
            "name": f"{nodename} Baseurl",
            "unique_id": f"uid_{kioskbaseurlentity}",
            "state_topic": mh.mq.STATE_TOPIC,
            "command_topic": mh.mq.COMMAND_TOPIC,  # <--- Tells HA where to send UI changes
            "command_template": "{{ value }}",  # Sends just the raw string to the broker
            "min": 1,
            "max": 100,
            "icon": "mdi:text-box-edit",
            "mode": "text"
        }
        mh.mq.publish_discovery(discovery_payload)
        mh.mq.publish_state(p.kiosk_baseurl)
        time.sleep(1)
    else:
        log.item(f'HA baseurl already set as {p.kiosk_baseurl}')

    log.item(f"Kiosk dashboard passed to start browser: {p.kiosk_baseurl},{kioskname} with prefix {p.HAIP}")
    start_browser(p.kiosk_baseurl, kioskname)
    touch_thread(device, virtualtouch)
