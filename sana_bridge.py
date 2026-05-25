#!/usr/bin/env python3
"""
sana_bridge.py  –  SANA App ↔ Hardware Bridge
===============================================
Exposes REST API on port 5050 for the companion app.

Endpoints:
    GET  /status     → current node, heading, nav state
    GET  /events     → poll pending events (emergency, location_response)
    POST /command    → send command to glasses

Commands:
    new_destination  → glasses say "قل وجهتك" and listen via STT
    get_location     → glasses speak current location aloud + push event to app
    stop_navigation  → stop current navigation

All spoken output comes from glasses.
Emergency call is handled by the app after receiving the "emergency" event.
"""

import threading
import time
import queue
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── state ─────────────────────────────────────────────────────────────────────

_get_node        = lambda: "N1"
_get_heading     = lambda: "north"
_nav_active      = lambda: False
_nav_queue       = None
_trigger_stt_fn  = None   # callable: triggers STT listen on glasses
_announce_loc_fn = None   # callable: announces location from glasses

_event_queue: queue.Queue = queue.Queue()

app = Flask(__name__)
CORS(app)


# ── public API (called from sana_main.py) ─────────────────────────────────────

def register_state_callbacks(get_node_fn, get_heading_fn, nav_active_fn):
    global _get_node, _get_heading, _nav_active
    _get_node    = get_node_fn
    _get_heading = get_heading_fn
    _nav_active  = nav_active_fn


def register_nav_queue(nav_q: queue.Queue):
    global _nav_queue
    _nav_queue = nav_q


def register_action_callbacks(trigger_stt_fn, announce_loc_fn):
    """
    Register callbacks so bridge can trigger hardware actions.
    trigger_stt_fn  : callable() → starts STT listening on glasses
    announce_loc_fn : callable() → glasses speak current location aloud
    """
    global _trigger_stt_fn, _announce_loc_fn
    _trigger_stt_fn  = trigger_stt_fn
    _announce_loc_fn = announce_loc_fn


def push_event(event: dict):
    event["ts"] = time.time()
    _event_queue.put(event)


def start_bridge(host="0.0.0.0", port=5050):
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    t.start()
    print(f"[BRIDGE] Running on http://{host}:{port}", flush=True)


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/status")
def status():
    return jsonify({
        "node":       _get_node(),
        "heading":    _get_heading(),
        "nav_active": _nav_active(),
        "ts":         time.time(),
    })


@app.route("/events")
def events():
    pending = []
    while not _event_queue.empty():
        try:
            pending.append(_event_queue.get_nowait())
        except queue.Empty:
            break
    return jsonify({"events": pending})


@app.route("/command", methods=["POST"])
def command():
    data = request.get_json(force=True, silent=True) or {}
    cmd  = data.get("cmd", "")

    # ── App → glasses: start STT to get new destination ──────────────────────
    if cmd == "new_destination":
        if _trigger_stt_fn is not None:
            threading.Thread(target=_trigger_stt_fn, daemon=True).start()
            return jsonify({"ok": True, "msg": "STT triggered on glasses"})
        elif _nav_queue is not None:
            # Fallback: put navigation trigger in queue
            _nav_queue.put({"type": "trigger_stt"})
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "STT not registered"}), 503

    # ── App → glasses: speak current location aloud ───────────────────────────
    elif cmd == "get_location":
        if _announce_loc_fn is not None:
            threading.Thread(target=_announce_loc_fn, daemon=True).start()
            return jsonify({"ok": True, "msg": "Location announced on glasses"})
        elif _nav_queue is not None:
            _nav_queue.put({"type": "get_location"})
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "location callback not registered"}), 503

    # ── App → glasses: stop navigation ───────────────────────────────────────
    elif cmd == "stop_navigation":
        if _nav_queue is not None:
            _nav_queue.put({"type": "stop_navigation"})
        push_event({"type": "stop_navigation"})
        return jsonify({"ok": True})

    return jsonify({"ok": False, "error": f"unknown cmd: {cmd}"}), 400


@app.route("/internal/event", methods=["POST"])
def internal_event():
    data = request.get_json(force=True, silent=True) or {}
    push_event(data)
    return jsonify({"ok": True})


if __name__ == "__main__":
    print("[BRIDGE] Standalone test mode")
    start_bridge()
    while True:
        time.sleep(1)
