#/usr/bin/env python3

import threading
import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
from evdev import InputDevice, ecodes
import subprocess
import os, glob

nodename = os.uname().nodename
MQTT_HOST = "pdxhome.pdxhome"
TOPIC_TOUCH = f"wallpanel/{nodename}/touch"
TOPIC_BRIGHTNESS = f"wallpanel/{nodename}/brightness"
print(f"Topic: {TOPIC_BRIGHTNESS}")

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
                with open(brightness_file, "w") as f:
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
    try:
        value = int(msg.payload.decode())
        print(f"Bright req: {msg.payload.decode()}  {value}")
        value = max(0, min(255, value))
        set_brightness(value)
    except Exception as e:
        print("[brightness] Error:", e)


def mqtt_thread():
    client = mqtt.Client()
    client.connect(MQTT_HOST)
    client.subscribe(TOPIC_BRIGHTNESS)
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


# ---------------------------
# Start both threads
# ---------------------------
if __name__ == "__main__":
    threading.Thread(target=mqtt_thread, daemon=True).start()
    touch_thread()
