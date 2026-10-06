import kiosklog as log
from evdev import InputDevice, ecodes, categorize, UInput
import glob, os, time
import panelbrightness as pb
import mqtthandling as mh
import parameters as p

resetcorner = ((0,0),(0,0))
restart_browser = None
kioskname = ''

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
                            restart_browser(p.kiosk_baseurl, kioskname)
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
