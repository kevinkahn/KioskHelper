import paho.mqtt.client as mqtt
import paho.mqtt.publish as publish
import kiosklog as log
import panelbrightness as pb
import parameters as p
import subprocess
import time
import json


class mqtt_handler:
    def __init__(self, nodename, locationgp, HA_ID, kioskbaseurlentity):
        self.MQTT_HOST = "mqtt"

        self.TOPIC_TOUCH = f"wallpanel/{nodename}/touch"
        self.TOPIC_HAIP = f"wallpanel/{nodename}/haip-{locationgp}"

        self.TOPIC_CONTROL = f"wallpanel/{nodename}/control"
        self.TOPIC_GP_CONTROL = f"wallpanel/{locationgp}/control"
        self.TOPIC_ALL_CONTROL = f"wallpanel/all/control"

        self.TOPIC_SCREENLEVEL = f"wallpanel/{nodename}/screenlevel"
        self.TOPIC_GP_SCREENLEVEL = f"wallpanel/{locationgp}/screenlevel"
        self.TOPIC_ALL_SCREENLEVEL = f"wallpanel/all/screenlevel"

        self.DISCOVERY_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/config"
        self.STATE_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/state"
        self.COMMAND_TOPIC = f"{HA_ID}/text/{kioskbaseurlentity}/set"

        self.CONTROL_TOPICS = [self.TOPIC_CONTROL, self.TOPIC_GP_CONTROL, self.TOPIC_ALL_CONTROL]
        self.BRIGHTNESS_TOPICS = [self.TOPIC_SCREENLEVEL, self.TOPIC_GP_SCREENLEVEL, self.TOPIC_ALL_SCREENLEVEL]

        self.nodename = nodename


    def on_message(self, client, userdata, msg):
        try:
            topic = msg.topic
            log.item(f'[on_message] Topic: {topic} {msg.payload.decode()}')
            if topic in self.BRIGHTNESS_TOPICS:
                rawvalue = msg.payload.decode()
                value = [item.strip() for item in rawvalue.strip().split(',')]
                log.item(f"Screen level req: {msg.payload.decode()} with param: {value}")
                if len(value) != 2:
                    value = ['ERROR', 0]
                if value[0] == 'dim':
                    pb.bm.setidlescreenlevel(max(0, min(255, int(value[1]))))
                elif value[0] == 'active':
                    pb.bm.setactivescreenlevel(max(0, min(255, int(value[1]))))
                elif value[0] == 'timeout':
                    pb.bm.screenreturntodim(int(value[1]))
                else:
                    log.item(f"Unknown brightness command: {value}")
            elif topic in self.CONTROL_TOPICS:
                rawvalue = msg.payload.decode()
                value = [item.strip() for item in rawvalue.strip().split(',')]
                log.item(f"[on_message] Control Topic: {topic}  {value}")
                if value[0] == 'reboot':
                    log.item("[reboot] Reboot node")
                    subprocess.run(["sudo", "reboot"])
                elif value[0] == 'restart':
                    log.item("[restart] Restart kiosk")
                    subprocess.run(["systemctl", "--user", "restart", "panel"])
                elif value[0] == 'update':
                    log.item("[update] Update kiosk")
                    subprocess.run(["git", "fetch"], cwd="/home/pi/kiosk")
                    subprocess.run(["git", "reset", "--hard"], cwd="/home/pi/kiosk")
                    subprocess.run(["git", "pull"], cwd="/home/pi/kiosk")
                    log.item("[restart] Restart kiosk")
                    subprocess.run(["systemctl","--user","restart","panel"])
                elif value[0] == 'loglevel':
                    log.LogLevel = int(value[1])
                    log.item(f"[loglevel] Set loglevel to {value[1]}")
                else:
                    log.item(f"[on_message] Unknown MQTT command: {topic}:  {value}")
            elif topic == self.STATE_TOPIC:
                value = msg.payload.decode()
                log.item(f"[on_message] State Topic: {topic}  {value}")
                # normalize to ip number so as not to confuse browser local storage
                p.kiosk_baseurl = f"{value.partition("8123")[2]}"
                log.item(f"[on_message] Base url: {p.kiosk_baseurl}")
            elif topic == self.TOPIC_HAIP:
                p.HAIP = msg.payload.decode()
                log.item(f"[on_message] TOPIC_HAIP Home Assistant IP: {p.HAIP}")
            else:
                log.item(f"[on_message] Unknown MQTT topic: {topic} with value: {msg.payload.decode()}")

        except Exception as e:
            log.item(f"MQTT Error {e}")

    def returntobaseurl(self):
        publish.single(f"wallpanel/{self.nodename}/returntobase", hostname=self.MQTT_HOST)
        log.item(f"Return to baseurl: {self.MQTT_HOST}",level=3)

    def sendbrowsercontrol(self, command):
        publish.single(f"wallpanel/{self.nodename}/browserctl", payload=command, hostname=self.MQTT_HOST)
        log.item(f"sendbrowsercontrol command: {command}", level=2)

    def get_HAIP(self):
        publish.single(f"{self.TOPIC_HAIP}-req", p.HAIP, hostname=self.MQTT_HOST)
        msgwait = -1
        while p.HAIP == "0.0.0.0":
            if msgwait < 0:
                log.item("Waiting HA IP - rerequesting")
                publish.single(f"{self.TOPIC_HAIP}-req", p.HAIP, hostname=self.MQTT_HOST)
                msgwait = 30
            else:
                msgwait -= 1
            time.sleep(1)
        return

    def publish_discovery(self, discovery_payload):
        log.item(f"Publish discovery message: {discovery_payload}")
        publish.single(self.DISCOVERY_TOPIC, json.dumps(discovery_payload), hostname=self.MQTT_HOST, retain=True)

    def publish_state(self, baseurl):
        log.item(f"Publish state message: {baseurl}")
        publish.single(self.STATE_TOPIC, baseurl, hostname=self.MQTT_HOST, retain=True)

    def mqtt_thread(self):
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        client.connect(self.MQTT_HOST)
        for topic in self.CONTROL_TOPICS:
            log.item(f"Subscribe to topic: {topic}")
            client.subscribe(topic)
        for topic in self.BRIGHTNESS_TOPICS:
            log.item(f"Subscribe to topic: {topic}")
            client.subscribe(topic)
        log.item(f"Subscribe to topic: {self.STATE_TOPIC}")
        client.subscribe(self.STATE_TOPIC)
        log.item(f"Subscribe to topic: {self.TOPIC_HAIP}")
        client.subscribe(self.TOPIC_HAIP)
        log.item("Subscribed to all topics")
        client.on_message = self.on_message
        client.loop_forever()

mq: mqtt_handler | None = None
