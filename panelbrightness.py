import os
import threading
import kiosklog as log

issuebrowsercontrol: None

class BrightnessManager:
    def __init__(self, timeout=10):
        self.timer = None
        self.lock = threading.Lock()
        self.touchesactive = False
        self.idlescreenlevel = 100
        self.activescreenlevel = 100
        self.screenreturntodim = timeout
        self.set_brightness(self.idlescreenlevel)
        self.screenisdim = (self.activescreenlevel == self.idlescreenlevel)

    def setdefaultlevel(self, value):
        self.idlescreenlevel = value
        self.set_brightness(self.idlescreenlevel)
        self.screenisdim = True

    def settimeout(self, value):
        self.screenreturntodim = value

    def setactivebrightness(self, value):
        self.activescreenlevel = value

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
                    log.item(f"Got {v} ", level=3)
                    return int(v)
                except Exception as e:
                    log.item(f"[brightness] Failed reading from {brightness_file}: {e}")
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
                    log.item(f"[brightness] Set {dev} to {value}")
                except Exception as e:
                    log.item(f"[brightness] Failed writing to {brightness_file}: {e}")

    def restore_brightness(self):
        with self.lock:
            log.item(f"Restore to {self.idlescreenlevel}")
            self.set_brightness(self.idlescreenlevel)
            self.screenisdim = True
            if issuebrowsercontrol is not None:
                issuebrowsercontrol('gotourl')
            self.timer = None
            self.touchesactive = False

    def wake_screen(self):
        with self.lock:
            if self.get_brightness() == self.activescreenlevel:
                log.item(f"Already bright on touch ({self.activescreenlevel})")
                return
            else:
                log.item(f"Do brighten from {self.get_brightness()} to {self.activescreenlevel}")
            # First touch in sequence
            if not self.touchesactive:
                self.touchesactive = True
                log.item(f"Touch while dim, set to  ({self.activescreenlevel})")
                self.set_brightness(self.activescreenlevel)  # temporary brightness
                self.screenisdim = False

            # Reset timer
            if self.timer is not None:
                log.item(f"Reset timer for touch while active")
                self.timer.cancel()

            self.timer = threading.Timer(self.screenreturntodim, self.restore_brightness)
            self.timer.daemon = True
            self.timer.start()