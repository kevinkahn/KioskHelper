import os
import threading

issuebrowsercontrol: None

class BrightnessManager:
    def __init__(self, timeout=10):
        self.timer = None
        self.lock = threading.Lock()
        self.touchesactive = False
        self.screenbrightness = 100
        self.activebrightness = 100
        self.screenreturntodim = timeout

    def setdefaultlevel(self, value):
        self.screenbrightness = value
        self.set_brightness(self.screenbrightness)

    def settimeout(self, value):
        self.screenreturntodim = value

    def setactivebrightness(self, value):
        self.activebrightness = value

    @staticmethod
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
        return 100

    @staticmethod
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
                except Exception as e:
                    print(f"[brightness] Failed writing to {brightness_file}: {e}")

    def restore_brightness(self):
        with self.lock:
            self.set_brightness(self.screenbrightness)
            if issuebrowsercontrol is not None:
                issuebrowsercontrol('gotourl')
            self.timer = None

    def touch_detected(self):
        with self.lock:
            # First touch in sequence
            if not self.touchesactive:
                self.set_brightness(self.activebrightness)  # temporary brightness

            # Reset timer
            if self.timer is not None:
                self.timer.cancel()

            self.timer = threading.Timer(self.screenreturntodim, self.restore_brightness)
            self.timer.daemon = True
            self.timer.start()