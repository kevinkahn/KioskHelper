#!/usr/bin/env bash
#git clone https://github.com/kevinkahn/KioskHelper.git /home/pi/kiosk
cd ~
mkdir -p ~/bin
mkdir -p ~/.config/systemd/user
cd kiosk
mv kiosk.service ~/.config/systemd/user
mv panel.service ~/.config/systemd/user
chmod +x panel_events.py kiosk.sh
mv panel_events.py ~/bin
mv kiosk.sh ~/bin
python3 -m venv /home/pi/kiosk/venv
source /home/pi/kiosk/venv/bin/activate
pip install --upgrade pip
pip install paho-mqtt evdev
systemctl --user daemon-reload
systemctl --user enable kiosk.service
systemctl --user enable panel.service
systemctl --user start kiosk.service
systemctl --user start panel.service
loginctl enable-linger pi




