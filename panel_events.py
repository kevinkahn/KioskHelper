#/usr/bin/env python3
import json
import subprocess
import threading
import panelbrightness as pb

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from evdev import InputDevice, ecodes
import socket
import os, glob, time, sys
import signal
from pathlib import Path


def handle_sigterm(signum, frame):
    """Callback function triggered when SIGTERM is received."""
    print(f"Received SIGTERM (signal {signum}). Cleaning up resources...")
    try:
        browser.terminate()
        print("Terminated browser")
    except Exception as e:
        print(f"Failed to terminate browser: {e}")
    sys.exit(0)

def get_local_ip_gp():
    # return the local net number for choosing local HA
   s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
   try:
     # Does not have to be reachable to extract the local interface IP
        s.connect(('8.8.8.8', 1))
        ip = s.getsockname()[0]
   except Exception:
        ip = '127.0.0.1'
   finally:
        s.close()
   return int(ip.split('.')[2])

signal.signal(signal.SIGTERM, handle_sigterm)

browser = None
localnetcode = get_local_ip_gp()

# Node name is pi dns name
nodename = os.uname().nodename
# Kiosk name is the name for the browser in HA
kioskname = f"kiosk_{nodename.replace('rpi_','')}"
kioskbaseurlentity = f"{kioskname}_baseurl"
kiosk_baseurl = None  # actual url once established running

locationgp = ('error', 'pdx', 'pgaw')[localnetcode] # user for group browser commands
MQTT_HOST = "mqtt"
HA_ID = ('error','HASS','HASSpga')[localnetcode]

# MQTT topics
TOPIC_TOUCH = f"wallpanel/{nodename}/touch"

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
                print(f"[touch] Using {dev} ({name})")
                return dev

        except Exception:
            continue

    print("[touch] No touchscreen found, falling back to event0")
    return "/dev/input/event0"

# ---------------------------
# MQTT Brightness Listener
# ---------------------------
def on_message(client, userdata, msg):
    global kiosk_baseurl, HAIP
    try:
        topic = msg.topic
        print(f'[on_message] Topic: {topic}')
        if topic == TOPIC_BRIGHTNESS:
            value = int(msg.payload.decode())
            print(f"Bright req: {msg.payload.decode()}  {value}")
            value = max(0, min(255, value))
            pb.set_brightness(value)
        elif topic == TOPIC_CONTROL:
            value = msg.payload.decode()
            print(f"[on_message] Control Topic: x{topic}x  x{value}x")
            if value == 'reboot':
                print("[reboot] Reboot node")
                subprocess.run(["sudo", "reboot"])
            elif value == 'restart':
                print("[restart] Restart kiosk")
                subprocess.run(["systemctl", "--user", "restart", "panel"])
            else:
                print(f"[on_message] Unknown MQTT command: {value}")
        elif topic == STATE_TOPIC:
            value = msg.payload.decode()
            print(f"[on_message] Announce Topic: {topic}  {value}")
            # normalize to ip number so as not to confuse browser local storage
            kiosk_baseurl = f"{HAIP}:8123{value.partition("8123")[2]}"
        elif topic == "homeassistant/ip":
            HAIP = msg.payload.decode()
            print(f"[homeassistant/ip] Home Assistant IP: {HAIP}")



    except Exception as e:
        print(f"MQTT Error {e}")


def mqtt_thread():
    client = mqtt.Client()
    client.connect(MQTT_HOST)
    for topic in CONTROL_TOPICS:
        client.subscribe(topic)
    for topic in BRIGHTNESS_TOPICS:
        client.subscribe(topic)
    client.subscribe(STATE_TOPIC)
    client.subscribe("homeassistant/ip")
    print("Subscribed to all topics")
    client.on_message = on_message
    client.loop_forever()


# ---------------------------
# Touch Listener
# ---------------------------
def touch_thread():
    event_dev = find_touchscreen_event()
    dev = InputDevice(event_dev)

    print("[touch] Listener started")

    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY and event.value == 1:
            v = pb.get_brightness()
            publish.single(TOPIC_TOUCH, str(v), hostname=MQTT_HOST)
            print(f"{v} Touch event sent")

def initialize_browser_environment(profile_dir):
    print("[initialize_browser_environment] Initializing")
    browser = subprocess.run([
        "/usr/lib/chromium/chromium",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--password-store=basic",
        f"--user-data-dir={profile_dir}",
        f"{HAIP}:8123/lovelace/0"])
    print("Output:", browser.stdout)
    print("Errors:", browser.stderr)
    print("Exit Code:", browser.returncode)
    print("Finished first time run")

    # Remove lingering Chromium lock files before starting
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        file_path = os.path.join(profile_dir, lock_file)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


def start_browser(url, nodename):
    print(f"[start_browser] Starting in {url}")

    profile_dir = "/home/pi/.config/chromium-kioskscreen"
    profilepath = Path(profile_dir)
    if not profilepath.is_dir():
        initialize_browser_environment(profile_dir)

    browser = subprocess.Popen([
        "/usr/lib/chromium/chromium",
        "--kiosk",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--password-store=basic",
        "--user-data-dir=/home/pi/.config/chromium-kioskscreen",
        url] )
    print("Browser started")
    return browser

    '''
    try:
        result = subprocess.run(['bash', '/home/pi/bin/kiosk.sh'], capture_output=True, text=True)
        print("Cleaned up")
        print("STDOUT:", result.stdout)
        print("STDERR:", result.stderr)
    except Exception as e:
        print(f"Cleaned up: {e}")
    '''


# ---------------------------
# Start both threads
# ---------------------------
if __name__ == "__main__":
    pb.set_brightness(255)
    threading.Thread(target=mqtt_thread, daemon=True).start()
    print('started listener')
    time.sleep(1)

    msgwait = -1
    if kiosk_baseurl is None: # haven't set up this kiosk in HA yet else retained MQTT message would have set this
        print('Initializing kiosk in HA')
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
        kiosk_baseurl = "unset"
        publish.single(STATE_TOPIC, kiosk_baseurl, hostname=MQTT_HOST, retain=True)
        time.sleep(1)

    while kiosk_baseurl == "unset":
        if msgwait < 0:
            print("Waiting for real baseurl to set")
            msgwait = 30
        else:
            msgwait -= 1
        time.sleep(1)
    print(f"Kiosk dashboard passed to start browser: {kiosk_baseurl}")
    browser = start_browser(kiosk_baseurl, nodename)
    touch_thread()
