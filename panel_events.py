#/usr/bin/env python3
import json
import subprocess
import threading
from random import randint

import panelbrightness as pb
import mqtthandling as mh
import kiosklog as log
import re
import parameters as p
import touchhandling as th

import socket
import os, time, sys
import signal
from pathlib import Path
from datetime import datetime, timedelta
from notification import notify, clear

def get_local_ip_gp():
    # return the local net number for choosing local HA
    netnumber = 0
    while netnumber == 0:
        time.sleep(3)
        log.item(f"[get_local_ip_gp] Try getting local ip address")

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
         # Does not have to be reachable to extract the local interface IP
            s.connect(('8.8.8.8', 1))
            ip = s.getsockname()[0]
            log.item(f"Local IP address: {ip}")
        except Exception as e:
            log.item(f"Failed to get local ip address: {e}")
            ip = '127.0.0.1'
        finally:
            s.close()
        netnumber = int(ip.split('.')[2])

    return netnumber

browser: subprocess.Popen | None = None

def handle_sigterm(signum, _frame):
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

def monitor_thread(target_thread, check_interval=5):
    log.item(f"Monitoring {target_thread.name} thread with check interval: {check_interval}")
    while True:
        target_thread.join(timeout=check_interval)
        if time.time() - mh.mq.lastmessagetime > 64800: # 18 hours
            log.item(f'MQTT Quiet for 18 hours!')
            mh.mq.lastmessagetime = time.time()
        if not target_thread.is_alive():
            # Trigger your alert here
            log.item(f"[ALERT] The MQTT thread has unexpectedly terminated!")
            break
    sys.exit(99)

def initialize_browser_environment(profile_dir, kiosknm, haip):
    initurl = f"{haip}/lovelace/0?BrowserID={kiosknm}"
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


def start_browser(burl, kiosknm, haip):
    url = f"{haip}{burl}"
    profile_dir = "/home/pi/.config/chromium-kioskscreen"
    profilepath = Path(profile_dir)
    if not profilepath.is_dir():
        log.item(f"Initializing chromium profile (Dir: {profile_dir}) Kiosk: {kiosknm} IP: {haip}")
        initialize_browser_environment(profile_dir, kiosknm, haip)

    log.item(f"[start_browser] Starting in {url}")
    p.browser = subprocess.Popen([
        "/usr/lib/chromium/chromium",
        "--kiosk",
        "--nocursor",
        "--no-first-run",
        "--hide-scrollbars",
        "--disable-smooth-scrolling",
        "--no-default-browser-check",
        "--noerrdialogs",
        "--disable-infobars",
        "--gpu-no-context-lost",
        "--disable-gpu-vsync=false",
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

def periodic_browser_restart(timelist, haip):
    log.item(f"Restart browser at {timelist}")
    while True:
        sleep_duration = (get_seconds_until_next(timelist))
        jitter = randint(0, 120)
        log.item(f"Sleeping efficiently for {sleep_duration} + {jitter} seconds")
        time.sleep(sleep_duration + jitter)
        log.item(f"Periodic browser restart at {datetime.now().strftime('%H:%M:%S')}")
        p.browser.kill()
        time.sleep(5)
        start_browser(p.kiosk_reduced_baseurl, kioskname, haip)


if __name__ == "__main__":

    # Rotate logs
    log.rotate_logs()
    log.item("Kiosk Starting")

    # Get kiosk IP and name
    localnetcode = get_local_ip_gp()
    log.item(f"Local ip network: {localnetcode}")
    nodename = os.uname().nodename

    # Kiosk name is the name for the browser in HA (strip the rpu-)
    kioskname = f"kiosk_{nodename.replace('rpi-', '')}"
    kioskbaseurlentity = f"{kioskname}_baseurl"
    log.item(
        f"Kiosk Info: node: {nodename} kioskname: {kioskname} kioskbaseurlentity: {kioskbaseurlentity} kiosk_baseurl: {p.kiosk_baseurl}",
        level=3)

    locationgp = ('error', 'pdx', 'pgaw')[localnetcode]  # user for group browser commands
    HA_ID = ('error', 'HASS', 'HASSpga')[localnetcode]
    log.item(f"Using local network: {localnetcode} Local group: {locationgp} HA Name: {HA_ID}")

    # Fix access issue
    subprocess.run(["sudo", "chgrp", "input", "/dev/uinput"])
    subprocess.run(["sudo", "chmod", "g+rw", "/dev/uinput"])

    # Check for periodic restarts
    browserrestarttimes = []

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
    if not browserrestarttimes:
        log.item(f"No browser periodic restart")
    else:
        log.item(f"Browser restart times: {browserrestarttimes}")


    # Get pi information for lighter weight browser
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
    if model in  ("3 Model B Plus", "3 Model B"):
        extrachromeflags = [ "--disable-low-res-tiling","--enable-low-end-device-mode",
                            "--disable-composited-antialiasing",
                            "--enable-oop-rasterization","--disable-background-networking","--disable-component-update",
                            "--animation-duration-scale=0","--wm-window-animations-disabled",
                            "--disable-software-compositing-surface","--disable-gpu-vsync=false"]
        log.item(f"Suppress gpu: {extrachromeflags}")
    else:
        extrachromeflags = []

    # Lock the touchscreen to prevent browser from using it directly
    device, virtualtouch = th.GrabTouchScreen()

    # Set up mqtt and brightness managers
    mh.mq = mh.mqtt_handler(nodename, locationgp, HA_ID, kioskbaseurlentity)
    pb.bm = pb.BrightnessManager(15, mh.mq.sendbrowsercontrol)
    mqttthread:threading.Thread = threading.Thread(target=mh.mq.mqtt_thread, daemon=True)
    mqttthread.start()
    log.item('Started MQTT handler')
    time.sleep(5)  # give things a chance to initialize

    # Get the IP of the HA instance
    HAIP = mh.mq.get_HAIP()

    th.restart_browser = start_browser
    th.kioskname = kioskname
    if browserrestarttimes:
        log.item("Start Browser Restart Thread")
        threading.Thread(target=periodic_browser_restart, args=(browserrestarttimes,)).start()

    if p.kiosk_baseurl == '':
    # haven't set up this kiosk in HA yet else retained MQTT message would have set this
        log.item('Initializing kiosk in HA')
        discovery_payload = {
            "name": f"{nodename} Baseurl",
            "unique_id": f"uid_{kioskbaseurlentity}",
            "state_topic": mh.mq.STATE_TOPIC,
            "command_topic": mh.mq.COMMAND_TOPIC,  # <--- Tells HA where to send UI changes
            "command_template": "{{ value }}",  # Sends just the raw string to the broker
            "mode": "text"
        }
        payload = json.dumps(discovery_payload)
        log.item(f"Dump as: {discovery_payload}")
        mh.mq.publish_discovery(discovery_payload)
        log.item(f"Set value for {nodename} Baseurl in Home Assistant")
        notify(f"Set value for text.{nodename.replace('-','_')}_baseurl")
        waittime = 0
        while p.kiosk_baseurl == '':
            time.sleep(30)
            waittime +=30
            notify(f"Still waiting {waittime} for text.{nodename.replace('-','_')}_baseurl")
            log.item(f'Still waiting {waittime} for text.{nodename.replace('-','_')}_baseurl')
        clear()
        #mh.mq.publish_state(p.kiosk_baseurl)
        time.sleep(1)
    else:
        log.item(f'HA baseurl already set as {p.kiosk_baseurl}')

    log.item(f"Kiosk dashboard passed to start browser: {p.kiosk_reduced_baseurl},{kioskname} with prefix {HAIP}")
    start_browser(p.kiosk_reduced_baseurl, kioskname, HAIP)

    th.touch_thread(device, virtualtouch)
