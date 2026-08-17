#!/bin/bash
 
# Change some Chromium prefs to clear out warning bars from displaying
sleep 5
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/' /home/user/.config/chromium/Default/Preferences
sed -i 's/"exit_type":"Crashed"/"exit_type":"Normal"/' /home/user/.config/chromium/Default/Preferences
echo "from kiosk.sh"
 

# Launch Chromium in Kiosk Mode
#/usr/bin/chromium --noerrdialogs --disable-infobars --kiosk http://hapdx.pdxhome:8123/ha-$HOSTNAME/0/?kiosk
