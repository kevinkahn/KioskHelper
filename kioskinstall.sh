#!/usr/bin/env bash
#git clone https://github.com/kevinkahn/KioskHelper.git /home/pi/kiosk
# info on cursor hiding https://www.google.com/search?q=hide+mouse+pointer+home+assistant+kiosk+mode+chromium+on+trixie&sca_esv=910d60152409f3a0&biw=2089&bih=1108&sxsrf=APpeQnuix5eEC9zdD9y2psKF25h9FSOcLQ%3A1786760709576&ei=Bc5_asPWIpun0PEPp7SumAc&ved=0ahUKEwiD7ZGryqGWAxWbEzQIHSeaC3MQ4dUDCBA&uact=5&oq=hide+mouse+pointer+home+assistant+kiosk+mode+chromium+on+trixie&gs_lp=Egxnd3Mtd2l6LXNlcnAiP2hpZGUgbW91c2UgcG9pbnRlciBob21lIGFzc2lzdGFudCBraW9zayBtb2RlIGNocm9taXVtIG9uIHRyaXhpZUj6bFDbLViCbHABeAGQAQCYAXigAecRqgEEMjEuNbgBA8gBAPgBAZgCGKAC4xDCAgoQABhHGNYEGLADwgIHECMYsAIYJ8ICCBAAGIAEGKIEwgIFEAAY7wXCAgoQIRgKGKABGMMEwgIEECEYCsICBRAhGKABwgIFECEYqwLCAgUQIRifBZgDAIgGAZAGCJIHBDE4LjagB-t7sgcEMTcuNrgH3xDCBwQ5LjE1yAchgAgB&sclient=gws-wiz-serp
cd ~
mkdir -p ~/bin
mkdir -p ~/.config/systemd/user
cd kiosk
mv panel.service ~/.config/systemd/user
chmod +x panel_events.py
mv panel_events.py ~/bin
python3 -m venv /home/pi/kiosk/venv
source /home/pi/kiosk/venv/bin/activate
pip install --upgrade pip
pip install paho-mqtt evdev
systemctl --user daemon-reload
systemctl --user enable panel.service
systemctl --user start panel.service
loginctl enable-linger pi
sudo apt install wtype
cd ~
cd .config/labwc
echo "sleep 1 && wtype -M logo -k h -m logo &" > autostart
echo "<labwc_config>
  <keyboard>
    <keybind key="W-h">
      <action name="HideCursor"/>
      <action name="WarpCursor" to="output" x="1" y="1"/>
    </keybind>
  </keyboard>
</labwc_config>
" >> rc.xml
echo "On pi desktop open browser with:"
echo "/usr/lib/chromium/chromium --user-deta-dir=/home/pi/.config/chromium-kioskscreen 192.168.1.15:8123?browser_ID=kiosk_dev7x"
echo "log in as kioskscreen, a"
echo "Open browser_mod from side panel and set the browser id in the name box"




