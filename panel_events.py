#/usr/bin/env python3
import json
import subprocess
import threading
import panelbrightness as pb
import kiosklog as log
import re

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from evdev import InputDevice, ecodes, categorize, UInput
import socket
import os, glob, time, sys
import signal
from pathlib import Path
from datetime import datetime, timedelta


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

signal.signal(signal.SIGTERM, handle_sigterm)

browser: subprocess.Popen | None = None
localnetcode = get_local_ip_gp()
screenbrightness = 100
screenreturntodim = 15
activebrightness = 100
resetcorner = ((0,0),(0,0))
browserretarttimes = ["03:14","11:15","17:30"]

# Node name is pi dns name
nodename = os.uname().nodename
# Kiosk name is the name for the browser in HA
kioskname = f"kiosk_{nodename.replace('rpi-','')}"
kioskbaseurlentity = f"{kioskname}_baseurl"
kiosk_baseurl = None  # actual url once established running
log.item(f"Kiosk Info: node: {nodename} kioskname: {kioskname} kioskbaseurlentity: {kioskbaseurlentity} kiosk_baseurl: {kiosk_baseurl}", level=3)

locationgp = ('error', 'pdx', 'pgaw')[localnetcode] # user for group browser commands
MQTT_HOST = "mqtt"
HA_ID = ('error','HASS','HASSpga')[localnetcode]
log.item(f"Using local network: {localnetcode} Local group: {locationgp} HA Name: {HA_ID}")

# MQTT topics
TOPIC_TOUCH = f"wallpanel/{nodename}/touch"
TOPIC_HAIP = f"wallpanel/{nodename}/haip-{locationgp}"

TOPIC_CONTROL = f"wallpanel/{nodename}/control"
TOPIC_GP_CONTROL = f"wallpanel/{locationgp}/control"
TOPIC_ALL_CONTROL = f"wallpanel/all/control"

TOPIC_BRIGHTNESS = f"wallpanel/{nodename}/brightness"
TOPIC_GP_BRIGHTNESS = f"wallpanel/{locationgp}/brightness"
TOPIC_ALL_BRIGHTNESS = f"wallpanel/all/brightness"

DISCOVERY_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/config"
STATE_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/state"
COMMAND_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/set"
HAIP="0.0.0.0"

CONTROL_TOPICS = [TOPIC_CONTROL, TOPIC_GP_CONTROL, TOPIC_ALL_CONTROL]
BRIGHTNESS_TOPICS = [TOPIC_BRIGHTNESS, TOPIC_GP_BRIGHTNESS, TOPIC_ALL_BRIGHTNESS]


def find_touchscreen_event():
    candidates = glob.glob("/dev/input/event*")

    for dev in candidates:
        name_path = f"/sys/class/input/{os.path.basename(dev)}/device/name"
        try:
            with open(name_path, "r") as f:
                name = f.read().strip().lower()

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
# MQTT Brightness Listener
# ---------------------------
def on_message(client, userdata, msg):
    global kiosk_baseurl, HAIP
    try:
        topic = msg.topic
        log.item(f'[on_message] Topic: {topic}')
        if topic in BRIGHTNESS_TOPICS:
            value = int(msg.payload.decode())
            log.item(f"Bright req: {msg.payload.decode()}  {value}")
            value = max(0, min(255, value))
            brightnessmgr.setdefaultlevel(value)
        elif topic in CONTROL_TOPICS:
            rawvalue = msg.payload.decode()
            value = [item.strip() for item in rawvalue.strip().split(',')]
            log.item(f"[on_message] Control Topic: {topic}  {value}")
            if value[0] == 'reboot':
                log.item("[reboot] Reboot node")
                subprocess.run(["sudo", "reboot"])
            elif value[0] == 'restart':
                log.item("[restart] Restart kiosk")
                subprocess.run(["systemctl", "--user", "restart", "panel"])
            elif value[0] == 'update':
                log.item("[update] Update kiosk")
                subprocess.run(["git", "fetch"], cwd="/home/pi/kiosk")
                subprocess.run(["git", "reset", "--hard"], cwd="/home/pi/kiosk")
                subprocess.run(["git", "pull"], cwd="/home/pi/kiosk")
                log.item("[restart] Restart kiosk")
                subprocess.run(["systemctl","--user","restart","panel"])
            elif value[0] == 'loglevel':
                log.LogLevel = int(value[1])
                log.item(f"[loglevel] Set loglevel to {value[1]}")
            else:
                log.item(f"[on_message] Unknown MQTT command: {topic}:  {value}")
        elif topic == STATE_TOPIC:
            value = msg.payload.decode()
            log.item(f"[on_message] State Topic: {topic}  {value}")
            # normalize to ip number so as not to confuse browser local storage
            kiosk_baseurl = f"{value.partition("8123")[2]}"
        elif topic == TOPIC_HAIP:
            HAIP = msg.payload.decode()
            log.item(f"[on_message] TOPIC_HAIP Home Assistant IP: {HAIP}")
        else:
            log.item(f"[on_message] Unknown MQTT topic: {topic} with value: {msg.payload.decode()}")





    except Exception as e:
        log.item(f"MQTT Error {e}")


def mqtt_thread():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST)
    for topic in CONTROL_TOPICS:
        client.subscribe(topic)
    for topic in BRIGHTNESS_TOPICS:
        client.subscribe(topic)
    client.subscribe(STATE_TOPIC)
    client.subscribe(TOPIC_HAIP)
    log.item("Subscribed to all topics")
    client.on_message = on_message
    client.loop_forever()

def returntobaseurl():
    publish.single(f"wallpanel/{nodename}/returntobase", hostname=MQTT_HOST)

def sendbrowsercontrol(command):
    publish.single(f"wallpanel/{nodename}/browserctl", payload=command, hostname=MQTT_HOST)
    log.item(f"sendbrowsercontrol command: {command}",level=2)

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
    global browser
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
                if brightnessmgr.screenisdim:
                    brightnessmgr.wake_screen()
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
                    if direction in ("Down","Up"): sendbrowsercontrol("refresh")
                    if direction in ("Right","Left"): sendbrowsercontrol("maintenance")
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
                            browser.kill()
                            time.sleep(1)
                            browser = start_browser(kiosk_baseurl, kioskname)
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
    global HAIP
    initurl = f"{HAIP}/lovelace/0?BrowserID={kiosknm}"
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
    global HAIP, browser
    url = f"{HAIP}{burl}"
    profile_dir = "/home/pi/.config/chromium-kioskscreen"
    profilepath = Path(profile_dir)
    if not profilepath.is_dir():
        initialize_browser_environment(profile_dir, kiosknm)

    log.item(f"[start_browser] Starting in {url}")
    browser = subprocess.Popen([
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
    return browser

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
    global browser
    log.item(f"Restart browser at {timelist}")
    while True:
        sleep_duration = get_seconds_until_next(timelist)
        log.item(f"Sleeping efficiently for {sleep_duration} seconds...")
        time.sleep(sleep_duration)
        log.item(f"Periodic browser restart at {datetime.now().strftime('%H:%M:%S')}")
        browser.kill()
        time.sleep(1)
        browser = start_browser(kiosk_baseurl, kioskname)


# ---------------------------
# Start 3 threads
# ---------------------------
if __name__ == "__main__":
    log.rotate_logs()
    log.item(f"Kiosk starting with loglevel {log.LogLevel}")
    if os.path.exists("/home/pi/restarttimes.txt"):
        browserretarttimes = []
        with open("/home/pi/restarttimes.txt", "r") as f:
            for line in f:
                clean_line = line.strip()
                # Skip empty lines or comment lines
                if not clean_line or clean_line.startswith("#"):
                    continue
                # Basic validation: ensure it follows the format HH:MM
                try:
                    datetime.strptime(clean_line, "%H:%M")
                    browserretarttimes.append(clean_line)
                    log.item(f" -> Loaded target time: {clean_line}")
                except ValueError:
                    print(f" [Error] Skipping invalid format line: '{line.strip()}'")
    log.item(f"Browser retart times: {browserretarttimes}")


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
    dev, ui = GrabTouchScreen()
    brightnessmgr = pb.BrightnessManager(15)
    pb.issuebrowsercontrol = sendbrowsercontrol
    threading.Thread(target=mqtt_thread, daemon=True).start()
    log.item('Started MQTT handler')
    publish.single(f"{TOPIC_HAIP}-req", HAIP, hostname=MQTT_HOST)
    msgwait = -1
    while HAIP == "0.0.0.0":
        if msgwait  <0:
            log.item("Waiting HA IP - rerequesting")
            publish.single(f"{TOPIC_HAIP}-req", HAIP, hostname=MQTT_HOST)
            msgwait = 30
        else:
            msgwait -= 1
        time.sleep(1)
    log.item("Start Browser Restart Thread")
    threading.Thread(target=periodic_browser_restart, args=(browserretarttimes,)).start()


    if kiosk_baseurl is None: # haven't set up this kiosk in HA yet else retained MQTT message would have set this
        log.item('Initializing kiosk in HA')
        discovery_payload = {
            "name": f"{nodename} Baseurl",
            "unique_id": f"uid_{kioskbaseurlentity}",
            "state_topic": STATE_TOPIC,
            "command_topic": COMMAND_TOPIC,  # <--- Tells HA where to send UI changes
            "command_template": "{{ value }}",  # Sends just the raw string to the broker
            "min": 1,
            "max": 100,
            "icon": "mdi:text-box-edit",
            "mode": "text"
        }
        publish.single(DISCOVERY_TOPIC, json.dumps(discovery_payload), hostname=MQTT_HOST, retain=True)
        # now wait for user to set topic in HA
        publish.single(STATE_TOPIC, kiosk_baseurl, hostname=MQTT_HOST, retain=True)
        #publish.single(COMMAND_TOPIC, kiosk_baseurl, hostname=MQTT_HOST, retain=True)
        time.sleep(1)
    else:
        log.item(f'HA baseurl already set as {kiosk_baseurl}')

    log.item(f"Kiosk dashboard passed to start browser: {kiosk_baseurl},{kioskname}")
    browser = start_browser(kiosk_baseurl, kioskname)
    touch_thread(dev, ui)
