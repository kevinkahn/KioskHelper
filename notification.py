import kiosklog as log
from jeepney import DBusAddress, new_method_call
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import unwrap_msg  # Import the unwrapper
connection = None
notifications = None
last_id = None
# Define the standard freedesktop Notification interface
def notify(msg):
    global connection, notifications, last_id

    if last_id != None:
        clear(last_id)
        last_id = None

    notifications = DBusAddress(
        '/org/freedesktop/Notifications',
        bus_name='org.freedesktop.Notifications',
        interface='org.freedesktop.Notifications'
    )

    # Open a connection to the user session DBus
    connection = open_dbus_connection(bus='SESSION')

    # 1. CREATE AND SEND THE NOTIFICATION
    msg_notify = new_method_call(
        notifications,
        'Notify',
        'susssasa{sv}i',
        (
            "PythonScript",                        # app_name
            0,                                     # replaces_id
            "",                                    # app_icon
            "Kiosk Manager",                       # summary / title
            msg, # body text
            [],                                    # actions
            {},                                    # hints
            -1                                     # expire_timeout
        )
    )

    # Send the message and get the raw Message object
    reply_msg = connection.send_and_get_reply(msg_notify)

    # Unwrap the message object to get the tuple containing the integer ID
    last_id = unwrap_msg(reply_msg)[0]

def clear(id=None):
    global last_id
    if id != None:
        useid = id
    elif last_id != None:
        useid = last_id
    else:
        log.item("Called to clear notification with no id")
        return
    last_id = None
    msg_close = new_method_call(
        notifications,
        'CloseNotification',
        'u',
        (useid,)
        )

    connection.send_and_get_reply(msg_close)
    connection.close()

