from flask import Flask, jsonify
from gpiozero import Button
import threading

app = Flask(__name__)

BUTTON_GPIO_PIN = 17
button = Button(BUTTON_GPIO_PIN, pull_up=False)

last_command = None
click_count = 0
click_timer = None


def set_command(command):
    global last_command
    last_command = command
    print("Command:", command)


def process_clicks():
    global click_count

    count = click_count
    click_count = 0

    if count == 1:
        start_new_destination()

    elif count == 2:
        start_current_location()

    elif count == 3:
        set_command("emergency_call")


def on_click():
    global click_count, click_timer

    click_count += 1

    if click_timer is not None:
        click_timer.cancel()

    click_timer = threading.Timer(0.7, process_clicks)
    click_timer.start()


button.when_pressed = on_click


@app.route("/new-destination", methods=["POST"])
def new_destination():
    start_new_destination()
    return jsonify({"success": True})


@app.route("/current-location", methods=["POST"])
def current_location():
    start_current_location()
    return jsonify({"success": True})


@app.route("/last-command", methods=["GET"])
def get_last_command():
    global last_command

    command = last_command
    last_command = None

    return jsonify({"command": command})


def start_new_destination():
    print("Say your destination")
    # Put your current Pi destination code here


def start_current_location():
    print("Current location")
    # Put your current Pi location code here


if __name__ == "__main__":
    print("SANA glasses API running on port 5000")
    app.run(host="0.0.0.0", port=5000)