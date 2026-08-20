import os

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