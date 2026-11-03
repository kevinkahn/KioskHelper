#!/usr/bin/env bash
#git clone https://github.com/kevinkahn/KioskHelper.git /home/pi/kiosk
# info on cursor hiding https://www.google.com/search?q=hide+mouse+pointer+home+assistant+kiosk+mode+chromium+on+trixie&sca_esv=910d60152409f3a0&biw=2089&bih=1108&sxsrf=APpeQnuix5eEC9zdD9y2psKF25h9FSOcLQ%3A1786760709576&ei=Bc5_asPWIpun0PEPp7SumAc&ved=0ahUKEwiD7ZGryqGWAxWbEzQIHSeaC3MQ4dUDCBA&uact=5&oq=hide+mouse+pointer+home+assistant+kiosk+mode+chromium+on+trixie&gs_lp=Egxnd3Mtd2l6LXNlcnAiP2hpZGUgbW91c2UgcG9pbnRlciBob21lIGFzc2lzdGFudCBraW9zayBtb2RlIGNocm9taXVtIG9uIHRyaXhpZUj6bFDbLViCbHABeAGQAQCYAXigAecRqgEEMjEuNbgBA8gBAPgBAZgCGKAC4xDCAgoQABhHGNYEGLADwgIHECMYsAIYJ8ICCBAAGIAEGKIEwgIFEAAY7wXCAgoQIRgKGKABGMMEwgIEECEYCsICBRAhGKABwgIFECEYqwLCAgUQIRifBZgDAIgGAZAGCJIHBDE4LjagB-t7sgcEMTcuNrgH3xDCBwQ5LjE1yAchgAgB&sclient=gws-wiz-serp
cd ~
sudo usermod -a -G sudo pi
mkdir -p ~/bin
mkdir -p ~/.config/systemd/user
cd kiosk
mv bin/* ~/bin
chmod +x ~/bin/*
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
mv panel.service ~/.config/systemd/user
chmod +x panel_events.py
python3 -m venv /home/pi/kiosk/venv
source /home/pi/kiosk/venv/bin/activate
pip install --upgrade pip
pip install paho-mqtt evdev
pip install jeepney
sudo apt update && sudo apt install mako-notifier libnotify-bin
systemctl --user daemon-reload
systemctl --user enable panel.service
#systemctl --user start panel.service
loginctl enable-linger pi
sudo apt install wtype
cd ~
# ==============================================================================
# OPTIMIZATION BLOCK: Configure 2GB Zram for Raspberry Pi 3B / 3B+ (Non-Root Safe)
# ==============================================================================
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)

    if [[ "$PI_MODEL" =~ "Raspberry Pi 3 Model B" ]]; then
        echo "[+] Target identified as Raspberry Pi 3B/3B+."
        echo "[*] Setting up 2GB zram swap space optimization for Chromium..."

        # 1. Create the system directory safely using sudo
        sudo mkdir -p /etc/rpi/swap.conf.d

        # 2. Write the configuration file using sudo tee (avoids permission errors with redirections)
        cat << 'EOF' | sudo tee /etc/rpi/swap.conf.d/80-increase-zram.conf > /dev/null
[Zram]
Mechanism=zram
FixedSizeMiB=2048
MaxSizeMiB=2048
EOF

        # 3. Clean out legacy config files using sudo
        if [ -f /etc/systemd/zram-generator.conf ]; then
            sudo rm -f /etc/systemd/zram-generator.conf
        fi

        # 4. Force systemd to reload its layout generators using sudo
        sudo systemctl daemon-reload

        echo "[+] Zram optimization complete. (Will take effect after the next reboot)"
    else
        echo "[*] Skipping Zram optimization: Target hardware is not a Pi 3B/3B+ ($PI_MODEL)."
    fi
else
    echo "[-] Skipping Zram optimization: Cannot determine hardware model (missing device-tree layout)."
fi
# ==============================================================================

#cd .config/labwc
#echo "sleep 1 && wtype -M logo -k h -m logo &" > autostart
#echo "<labwc_config>
#  <keyboard>
#    <keybind key="W-h">
#      <action name="HideCursor"/>
#      <action name="WarpCursor" to="output" x="1" y="1"/>
#    </keybind>
#  </keyboard>
#</labwc_config>
#" >> rc.xml
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", OPTIONS+="static_node=uinput", TAG+="uaccess", GROUP="input", MODE="0660"' | sudo tee /etc/udev/rules.d/99-uinput.rules
echo 'ATTRS{name}=="Filtered Touchscreen Flipped", ENV{LIBINPUT_CALIBRATION_MATRIX}="-1 0 1 0 -1 1 0 0 1"' | sudo tee /etc/udev/rules.d/99-virtual-touchscreen.rules
echo "source .bashrc to get bin in path"
echo "As a backup:"
echo "/usr/lib/chromium/chromium --user-deta-dir=/home/pi/.config/chromium-kioskscreen 192.168.1.15:8123?browser_ID=kiosk_dev7x"
echo "log in as kioskscreen, a", then exit the browser
echo "Open browser_mod from side panel and set the browser id in the name box"
echo 'If need to invert touch screen: touch fliptouch in home dir'
echo "Do a reboot to reset the swap and then log into the browser"




