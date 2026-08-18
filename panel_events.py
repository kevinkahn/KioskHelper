#/usr/bin/env python3
import json
import subprocess
import threading
from signal import signal

import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from evdev import InputDevice, ecodes
import socket
import os, glob, time, sys
import signal

def handle_sigterm(signum, frame):
    """Callback function triggered when SIGTERM is received."""
    print(f"Received SIGTERM (signal {signum}). Cleaning up resources...")
    try:
        browser.terminate()
        print("Terminated browser")
    except Exception as e:
        print(f"Failed to terminate browser: {e}")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_sigterm)
browser = None
nodename = os.uname().nodename
entityprefix = f"kiosk_{nodename.replace('rpi_','')}"
entityid = f"{entityprefix}_baaseurl"
kiosk_baseurl = None
MQTT_HOST = "mqtt.pdxhome"
HA_ID = 'HASS'
TOPIC_TOUCH = f"wallpanel/{nodename}/touch"
TOPIC_BRIGHTNESS = f"wallpanel/{nodename}/brightness"
TOPIC_CONTROL = f"wallpanel/{nodename}/control"
TOPIC_ALL_BRIGHTNESS = f"wallpanel/all/brightness"
TOPIC_ALL_CONTROL = f"wallpanel/all/control"
DISCOVERY_TOPIC = f"{HA_ID}/text/{entityid}/config"
STATE_TOPIC = f"{HA_ID}/text/{entityid}/state"
COMMAND_TOPIC = f"{HA_ID}/text/{entityid}/set"


def get_local_ip_gp():
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

locationgp = ('error', 'pdx', 'pgaw')[get_local_ip_gp()]
TOPIC_GP_BRIGHTNESS = f"wallpanel/{locationgp}/brightness"
TOPIC_GP_CONTROL = f"wallpanel/{locationgp}/control"

CONTROL_TOPICS = [TOPIC_CONTROL, TOPIC_GP_CONTROL, TOPIC_ALL_CONTROL]
BRIGHTNESS_TOPICS = [TOPIC_BRIGHTNESS, TOPIC_GP_BRIGHTNESS, TOPIC_ALL_BRIGHTNESS]


def get_brightness():
    # 1. Check for kernel backlight devices
    backlight_root = "/sys/class/backlight"
    if os.path.isdir(backlight_root):
        devices = os.listdir(backlight_root)
        if devices:
            # Use the first available backlight device
            dev = devices[0]
            brightness_file = os.path.join(backlight_root, dev, "brightness")

            try:
                with open(brightness_file, "r") as f:
                    v = f.read()
                print(f"Got [v] ")
                return v
            except Exception as e:
                print(f"[brightness] Failed reading from {brightness_file}: {e}")

def set_brightness(value):
    # 1. Check for kernel backlight devices
    backlight_root = "/sys/class/backlight"
    if os.path.isdir(backlight_root):
        devices = os.listdir(backlight_root)
        if devices:
            # Use the first available backlight device
            dev = devices[0]
            brightness_file = os.path.join(backlight_root, dev, "brightness")

            try:
                with open(brightness_file, "w") as f:
                    f.write(str(value))
                print(f"[brightness] Set {dev} to {value}")
                return
            except Exception as e:
                print(f"[brightness] Failed writing to {brightness_file}: {e}")

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
    global kiosk_baseurl
    try:
        topic = msg.topic
        print(f'[on_message] Topic: {topic}')
        if topic == TOPIC_BRIGHTNESS:
            value = int(msg.payload.decode())
            print(f"Bright req: {msg.payload.decode()}  {value}")
            value = max(0, min(255, value))
            set_brightness(value)
        elif topic == TOPIC_CONTROL:
            value = msg.payload.decode()
            print(f"[on_message] Control Topic: x{topic}x  x{value}x")
            if value == 'reboot':
                print("[reboot] Rebooting")
                os.system("sudo reboot")
            elif value == 'restart':
                print("[shutdown] Restart")
                os.system("systemctl --user restart kiosk")
                os.system("systemctl --user restart panel")
            else:
                print(f"[on_message] Unknown MQTT command: {value}")
        elif topic == STATE_TOPIC:
            value = msg.payload.decode()
            print(f"[on_message] Announce Topic: {topic}  {value}")
            kiosk_baseurl = f"{value}"



    except Exception as e:
        print(f"MQTT Error {e}")


def mqtt_thread():
    client = mqtt.Client()
    client.connect(MQTT_HOST)
    for topic in CONTROL_TOPICS:
        print("Subscribing to topic", topic)
        client.subscribe(topic)
    for topic in BRIGHTNESS_TOPICS:
        print("Subscribing to topic", topic)
        client.subscribe(topic)
    print("Subscribing to topic", STATE_TOPIC)
    client.subscribe(STATE_TOPIC)
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
            v = get_brightness()
            publish.single(TOPIC_TOUCH, str(v), hostname=MQTT_HOST)
            print(f"{v} Touch event sent")

def start_browser(url, nodename):
    kioskid = f"kiosk_{nodename.replace('rpi-','')}"
    actualurl = f"{url}?browser_id={kioskid}"
    print(f"[start_browser] Starting in {actualurl}")

    browser = subprocess.Popen([
        "/usr/lib/chromium/chromium",
        "--kiosk",
        "--no-first-run",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--password-store=basic",
        "--user-data-dir=/home/pi/.config/chromium"
        #"--user-data-dir=/home/pi/.ha_chrome_profile"
        , actualurl] )
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
    set_brightness(255)
    threading.Thread(target=mqtt_thread, daemon=True).start()
    print('started listener')
    #publish.single('wallp/test/test','tesinp',hostname='pdxhome.pdxhome', retain=True)
    #publish.single(TOPIC_ANNOUNCE, "empty", hostname=MQTT_HOST)
    time.sleep(1)
    print(f"await")
    msgwait = -1
    if kiosk_baseurl is None:
        print('Initializing kiosk in HA')
        discovery_payload = {
            "name": f"{nodename} Baseurl",
            "unique_id": f"uid_{entityid}",
            "state_topic": STATE_TOPIC,
            "command_topic": COMMAND_TOPIC,  # <--- Tells HA where to send UI changes
            "command_template": "{{ value }}",  # Sends just the raw string to the broker
            "min": 1,
            "max": 100,
            "icon": "mdi:text-box-edit",
            "mode": "text"
        }
        print(f"discovery payload: {discovery_payload}")
        print(f"Discovery topic: {DISCOVERY_TOPIC}")
        publish.single(DISCOVERY_TOPIC, json.dumps(discovery_payload), hostname=MQTT_HOST, retain=True)
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
    print(f"Kiosk dashboard: {kiosk_baseurl}")
    browser = start_browser(kiosk_baseurl, nodename)
    touch_thread()
