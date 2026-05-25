#!/usr/bin/env python3
"""
sana_main.py – SANA Smart Glasses Main System
==============================================
Origin: Elevator = N1 (fixed)

Touch button hold durations:
    2 sec hold → new destination (STT listens)
    4 sec hold → exact location (glasses speak Arabic room name)
    6 sec hold → emergency (push event to app)

App commands (via bridge):
    new_destination → triggers STT on glasses
    get_location    → glasses speak location aloud + push event to app

All output spoken from glasses. Emergency call handled by app.
"""

import os
import sys
import time
import threading
import queue

from sana_pi5_yolo_ocr_live_runtime import (
    speak_text_ar,
    load_yolo_model,
    detect_objects,
    process_obstacles,
    choose_best_sign,
    process_sign_crop,
    crop_bbox,
    create_picamera2,
    picamera2_frame_to_bgr,
    YOLO_MODEL_PATH,
    LIVE_EVERY_N_FRAMES,
)

from navigation import (
    load_map,
    build_graph,
    dijkstra,
    get_node,
    get_edge_distance,
    get_edge_time,
    generate_instructions,
)

from sana_position     import PositionTracker
from sana_room_matcher import arabic_to_room_name, get_room_node_id, list_all_rooms

from sana_bridge import (
    start_bridge,
    push_event,
    register_state_callbacks,
    register_nav_queue,
    register_action_callbacks,
)

from gpiozero import OutputDevice, Button

VIBRATION_PIN      = 27
MAP_FILE           = "/home/sana/map.json"
ORIGIN_NODE        = "N1"
INSTRUCTION_PAUSE  = 4.0
TEST_MODE          = "--test" in sys.argv

# Hold thresholds in seconds
HOLD_DESTINATION   = 2.0
HOLD_LOCATION      = 4.0
HOLD_EMERGENCY     = 6.0

# Obstacle vibration cooldown – won't vibrate again within this many seconds
OBSTACLE_COOLDOWN  = 4.0

shutdown_event      = threading.Event()
navigation_active   = threading.Event()
stop_navigation     = threading.Event()
nav_pause_event     = threading.Event()
yolo_pause_event    = threading.Event()
yolo_speaking_event = threading.Event()
yolo_started        = False
map_data            = None
position_tracker    = None
stt_engine          = None
nav_queue_global    = None

# Ensures obstacle vibration fires only once per TTS warning
_obstacle_vib_fired = False
_vib_lock           = threading.Lock()

vibration_motor = OutputDevice(VIBRATION_PIN, active_high=True, initial_value=False)


# ── VIBRATION ─────────────────────────────────────────────────────────────────

def vibrate(duration: float = 0.2):
    try:
        vibration_motor.on()
        time.sleep(duration)
        vibration_motor.off()
    except Exception as e:
        print(f"[VIB] {e}", flush=True)
    finally:
        vibration_motor.off()


def vibrate_pattern(pattern: list):
    try:
        for i, dur in enumerate(pattern):
            if i % 2 == 0:
                vibration_motor.on()
            else:
                vibration_motor.off()
            time.sleep(dur)
    except Exception as e:
        print(f"[VIB] {e}", flush=True)
    finally:
        vibration_motor.off()


def vibrate_obstacle():
    """Vibrate once when TTS obstacle warning fires. Stops immediately after."""
    global _obstacle_vib_fired
    with _vib_lock:
        if _obstacle_vib_fired:
            return
        _obstacle_vib_fired = True
    vibrate(0.2)


def vibrate_obstacle_far():
    vibrate_obstacle()


def vibrate_obstacle_medium():
    vibrate_obstacle()


def vibrate_obstacle_danger():
    vibrate_obstacle()


# ── ROOM NAME HELPERS ─────────────────────────────────────────────────────────

def room_to_arabic(room_name: str) -> str:
    """Convert English room name to Arabic for TTS."""
    if not room_name:
        return ""

    number_words = {
        "1": "واحد", "2": "اثنين", "3": "ثلاثة", "4": "أربعة", "5": "خمسة",
        "6": "ستة", "7": "سبعة", "8": "ثمانية", "9": "تسعة", "10": "عشرة",
        "11": "أحد عشر", "12": "اثنا عشر", "13": "ثلاثة عشر", "14": "أربعة عشر",
        "15": "خمسة عشر", "16": "ستة عشر", "17": "سبعة عشر", "18": "ثمانية عشر",
        "19": "تسعة عشر", "20": "عشرين", "21": "واحد وعشرين", "22": "اثنين وعشرين",
        "23": "ثلاثة وعشرين", "24": "أربعة وعشرين", "25": "خمسة وعشرين",
        "26": "ستة وعشرين", "27": "سبعة وعشرين", "28": "ثمانية وعشرين",
        "29": "تسعة وعشرين", "30": "ثلاثين", "31": "واحد وثلاثين",
        "32": "اثنين وثلاثين", "33": "ثلاثة وثلاثين", "34": "أربعة وثلاثين",
        "35": "خمسة وثلاثين", "36": "ستة وثلاثين", "37": "سبعة وثلاثين",
        "38": "ثمانية وثلاثين", "39": "تسعة وثلاثين", "40": "أربعين",
        "41": "واحد وأربعين", "42": "اثنين وأربعين", "43": "ثلاثة وأربعين",
        "44": "أربعة وأربعين", "45": "خمسة وأربعين",
    }

    import re
    nums = re.findall(r"\d+", room_name)
    n    = nums[0] if nums else ""
    n_ar = number_words.get(n, n)

    if room_name == "Bathroom":
        return "الحمام"
    if room_name.startswith("Lab"):
        suffix = " أ" if room_name.endswith(" A") else " ب" if room_name.endswith(" B") else ""
        return f"مختبر {n_ar}{suffix}".strip()
    if room_name.startswith("Classroom"):
        return f"فصل {n_ar}".strip()
    if room_name.startswith("Office"):
        suffix = " أ" if room_name.endswith(" A") else " ب" if room_name.endswith(" B") else ""
        return f"مكتب {n_ar}{suffix}".strip()
    if room_name.startswith("IT Unit"):
        return f"وحدة تقنية {n_ar}".strip()
    if room_name.startswith("GP Experiment Room"):
        return "غرفة مشروع التخرج"
    return room_name


def room_name_for_current_node() -> str:
    """Return Arabic room name for current node, or corridor description."""
    if not position_tracker:
        return "المصعد"
    node = position_tracker.current_node
    if not map_data:
        return "موقع غير معروف"
    for room in map_data.get("rooms", []):
        if not isinstance(room, dict):
            continue
        room_node = (
            room.get("nodeId") or room.get("node_id") or
            room.get("node") or room.get("nearest_node")
        )
        if room_node == node:
            return room_to_arabic(room.get("name", ""))
    for n in map_data.get("nodes", []):
        if n.get("nodeId") == node:
            ntype = n.get("type", "")
            if ntype == "elevator":
                return "المصعد"
            elif ntype == "entrance":
                return "المدخل"
            elif ntype == "decision":
                return "تقاطع الممر"
            else:
                return "الممر"
    return "موقع غير معروف"


def announce_location():
    """Speak current location aloud and push to app."""
    yolo_pause_event.set()
    try:
        current_place = room_name_for_current_node()
        heading = position_tracker.get_heading_name() if position_tracker else "north"
        heading_ar = {
            "north": "الشمال", "east": "الشرق",
            "south": "الجنوب", "west":  "الغرب",
        }.get(heading, heading)

        speak_text_ar(f"موقعك الحالي هو {current_place}، واتجاهك نحو {heading_ar}")

        push_event({
            "type":       "location_response",
            "node":       position_tracker.current_node if position_tracker else ORIGIN_NODE,
            "heading":    heading,
            "heading_ar": heading_ar,
            "place":      current_place,
        })
    finally:
        yolo_pause_event.clear()


# ── TOUCH HOLD HANDLER ────────────────────────────────────────────────────────

def handle_hold_touch():
    """
    Measures how long touch button is held.
    2s → new destination
    4s → exact location
    6s → emergency
    Gives haptic feedback at each threshold.
    """
    press_time = time.time()
    notified   = set()

    try:
        btn = stt_engine._button if stt_engine else None
    except Exception:
        btn = None

    while True:
        held = time.time() - press_time

        if held >= HOLD_DESTINATION and "dest" not in notified:
            vibrate(0.15)
            notified.add("dest")

        if held >= HOLD_LOCATION and "loc" not in notified:
            vibrate_pattern([0.15, 0.1, 0.15])
            notified.add("loc")

        if held >= HOLD_EMERGENCY and "emer" not in notified:
            vibrate_pattern([0.15, 0.1, 0.15, 0.1, 0.15])
            notified.add("emer")

        if btn is not None:
            try:
                if not btn.is_pressed:
                    break
            except Exception:
                break
        else:
            break

        time.sleep(0.05)

    held = time.time() - press_time
    print(f"[TOUCH] Held {held:.1f}s", flush=True)

    if held >= HOLD_EMERGENCY:
        handle_touch_emergency()
    elif held >= HOLD_LOCATION:
        handle_touch_location()
    elif held >= HOLD_DESTINATION:
        handle_touch_destination()
    else:
        print(f"[TOUCH] Too short ({held:.1f}s) – ignored", flush=True)


def handle_touch_destination():
    """2s hold → new destination via STT."""
    print("[TOUCH] 2s → new destination", flush=True)
    if navigation_active.is_set():
        on_touch_interrupt()
    else:
        if stt_engine and not stt_engine._active_listening:
            threading.Thread(
                target=stt_engine._active_listen,
                kwargs={"trigger": "touch"},
                daemon=True,
            ).start()


def handle_touch_location():
    """4s hold → announce location."""
    print("[TOUCH] 4s → announce location", flush=True)
    threading.Thread(target=announce_location, daemon=True).start()


def handle_touch_emergency():
    """6s hold → emergency signal to app."""
    print("[TOUCH] 6s → emergency", flush=True)
    push_event({"type": "emergency"})
    yolo_pause_event.set()
    try:
        speak_text_ar("جارٍ الاتصال بجهة الطوارئ")
    finally:
        yolo_pause_event.clear()


# ── NAVIGATION ────────────────────────────────────────────────────────────────

def speak_route(instructions: list, route: list):
    navigation_active.set()
    stop_navigation.clear()

    try:
        for i, instruction in enumerate(instructions):
            if shutdown_event.is_set():
                break

            if stop_navigation.is_set():
                print("[NAV] Stopped by touch interrupt", flush=True)
                break

            while nav_pause_event.is_set() or yolo_speaking_event.is_set():
                time.sleep(0.2)

            yolo_pause_event.set()

            if position_tracker and i < len(route) - 1:
                dist = get_edge_distance(map_data, route[i], route[i + 1])
                position_tracker.set_expected_next(route[i + 1], dist)

                if "انعطف يمين" in instruction:
                    dirs = ["north", "east", "south", "west"]
                    cur  = position_tracker.get_heading_name()
                    position_tracker.update_heading(dirs[(dirs.index(cur) + 1) % 4])
                elif "انعطف يسار" in instruction:
                    dirs = ["north", "east", "south", "west"]
                    cur  = position_tracker.get_heading_name()
                    position_tracker.update_heading(dirs[(dirs.index(cur) - 1) % 4])

            print(f"[NAV] {instruction}", flush=True)
            speak_text_ar(instruction)

            yolo_pause_event.clear()

            # Use real edge timeSeconds from map; fall back to fixed pause if unavailable
            if i < len(route) - 1:
                edge_time = get_edge_time(map_data, route[i], route[i + 1])
                pause = edge_time if edge_time is not None else INSTRUCTION_PAUSE
            else:
                pause = INSTRUCTION_PAUSE

            time.sleep(pause)

            # Update current node to the node just reached after walking the segment
            if position_tracker and i < len(route) - 1:
                position_tracker.current_node = route[i + 1]

    finally:
        navigation_active.clear()
        stop_navigation.clear()
        yolo_pause_event.clear()
        vibration_motor.off()


def handle_navigation_request(arabic_text: str, english_room: str = ""):
    global yolo_started

    if not arabic_text:
        speak_text_ar("لم أفهم الوجهة، حاول مرة أخرى")
        return

    if navigation_active.is_set():
        print("[NAV] Stopping current route, rerouting...", flush=True)
        stop_navigation.set()
        navigation_active.clear()
        time.sleep(0.5)

    print(f"[NAV] Request: '{arabic_text}'", flush=True)

    if english_room:
        room_name = english_room
        print(f"[NAV] Room from STT: '{room_name}'", flush=True)
    else:
        room_name = arabic_to_room_name(arabic_text, map_data)
        print(f"[NAV] Matched room: '{room_name}'", flush=True)

    if not room_name:
        speak_text_ar("لم أجد هذا المكان، يمكنك طلب فصل أو مختبر أو مكتب أو حمام")
        return

    dest_node = get_room_node_id(room_name, map_data)
    if not dest_node:
        speak_text_ar("لم أجد موقع هذا المكان في الخريطة")
        return

    current_node = position_tracker.current_node if position_tracker else ORIGIN_NODE
    heading      = position_tracker.get_heading_name() if position_tracker else "north"

    print(f"[NAV] From: {current_node} (facing {heading}) → To: {dest_node} ({room_name})", flush=True)

    if current_node == dest_node:
        speak_text_ar("أنت بالفعل في هذا المكان")
        return

    spoken_room_name = room_to_arabic(room_name)
    speak_text_ar(f"جارٍ حساب المسار إلى {spoken_room_name}")
    graph = build_graph(map_data)
    route, total_distance = dijkstra(graph, current_node, dest_node)

    if route is None:
        speak_text_ar("لا يوجد مسار متاح لهذا المكان")
        return

    instructions = generate_instructions(map_data, route, heading)
    speak_text_ar(f"المسافة {round(total_distance)} متر")

    print(f"\n[NAV] ── Route ──────────────────────────────────────────", flush=True)
    print(f"[NAV] Path : {' → '.join(route)}", flush=True)
    print(f"[NAV] Dist : {round(total_distance)}m", flush=True)
    print(f"[NAV] Steps:", flush=True)
    for idx, instr in enumerate(instructions):
        print(f"       {idx+1}. {instr}", flush=True)
    print(f"[NAV] ────────────────────────────────────────────────────\n", flush=True)

    if not yolo_started:
        yolo_started = True
        if position_tracker:
            try:
                position_tracker.set_vibrate_callbacks(
                    vibrate_obstacle_far,
                    vibrate_obstacle_medium,
                    vibrate_obstacle_danger,
                )
                position_tracker.start_tof()
            except Exception as exc:
                print(f"[TOF] Could not start proximity haptics: {exc}", flush=True)
        threading.Thread(target=yolo_loop, daemon=True).start()
        print("[YOLO] Started after destination received.", flush=True)

    threading.Thread(
        target=speak_route,
        args=(instructions, route),
        daemon=True,
    ).start()


# ── TOUCH INTERRUPT ───────────────────────────────────────────────────────────

def on_touch_interrupt():
    if navigation_active.is_set():
        print("[TOUCH] Navigation interrupted", flush=True)
        stop_navigation.set()
        navigation_active.clear()
        yolo_pause_event.clear()
        vibration_motor.off()
        time.sleep(0.5)
        speak_text_ar("تم إيقاف التوجيه")
        if stt_engine is not None:
            threading.Thread(
                target=stt_engine._active_listen,
                kwargs={"trigger": "touch"},
                daemon=True,
            ).start()
        elif nav_queue_global is not None:
            nav_queue_global.put({"type": "interrupted"})


# ── YOLO LOOP ─────────────────────────────────────────────────────────────────

def yolo_loop():
    print("[YOLO] Starting background loop...", flush=True)
    picam2           = None
    frame_count      = 0
    sign_cooldown    = 0
    obstacle_cooldown = 0

    try:
        picam2 = create_picamera2()
        while not shutdown_event.is_set():

            if yolo_pause_event.is_set():
                time.sleep(0.2)
                continue

            rgb   = picam2.capture_array()
            frame = picamera2_frame_to_bgr(rgb)
            frame_count += 1

            if frame_count % max(1, LIVE_EVERY_N_FRAMES) != 0:
                time.sleep(0.01)
                continue

            detections = detect_objects(model_global, frame)
            if not detections:
                continue

            now = time.time()

            # Only process obstacles if cooldown has passed
            if now - obstacle_cooldown >= OBSTACLE_COOLDOWN:
                obstacle_cooldown = now
                _obstacle_vib_fired = False
                yolo_speaking_event.set()
                try:
                    process_obstacles(detections)
                finally:
                    yolo_speaking_event.clear()
                    vibration_motor.off()

            best_sign = choose_best_sign(detections)
            if best_sign and (now - sign_cooldown) > 15:
                sign_cooldown = now
                threading.Thread(
                    target=handle_sign,
                    args=(frame, best_sign),
                    daemon=True,
                ).start()

    except Exception as e:
        print(f"[YOLO] Error: {e}", flush=True)
    finally:
        vibration_motor.off()
        if picam2:
            try:
                picam2.stop()
            except Exception:
                pass


def handle_sign(frame, best_sign: dict):
    nav_pause_event.set()
    yolo_pause_event.set()
    try:
        vibrate(0.2)
        speak_text_ar("أرى لافتة أمامك، هل تريد قراءتها؟")

        if TEST_MODE:
            print("[TEST] Sign detected – auto-skipping in test mode", flush=True)
            return

        if stt_engine is not None:
            answer = stt_engine.listen_once()
            print(f"[SIGN] Answer: '{answer}'", flush=True)
            if any(w in answer for w in ["نعم", "أيوه", "اقرأ", "ايوه", "yes", "اه", "ايه"]):
                cropped = crop_bbox(frame, best_sign["bbox"])
                process_sign_crop(cropped, int(time.time()))
            else:
                speak_text_ar("حسناً، نكمل")
        else:
            time.sleep(3.0)

    finally:
        nav_pause_event.clear()
        yolo_pause_event.clear()
        vibration_motor.off()


# ── TEST MODE INPUT LOOP ───────────────────────────────────────────────────────

def test_input_loop(nav_queue: queue.Queue):
    print("\n" + "=" * 55, flush=True)
    print("  TEST MODE – type destination, 'pos', or 'quit'", flush=True)
    print("  Commands: stop | loc | emergency | rooms | pos", flush=True)
    print("=" * 55 + "\n", flush=True)

    while not shutdown_event.is_set():
        try:
            text = input("Destination > ").strip()
        except (EOFError, KeyboardInterrupt):
            shutdown_event.set()
            break

        if not text:
            continue
        if text.lower() == "quit":
            shutdown_event.set()
            break
        elif text.lower() == "pos":
            if position_tracker:
                print(f"[POS] Node={position_tracker.current_node} | "
                      f"Facing={position_tracker.get_heading_name()} | "
                      f"Walked={position_tracker.distance_walked:.1f}m", flush=True)
        elif text.lower() == "rooms":
            print("[ROOMS]", list_all_rooms(map_data), flush=True)
        elif text.lower() == "stop":
            on_touch_interrupt()
        elif text.lower() == "loc":
            threading.Thread(target=announce_location, daemon=True).start()
        elif text.lower() == "emergency":
            push_event({"type": "emergency"})
        else:
            nav_queue.put({"type": "navigation", "text": text})


# ── MAIN ──────────────────────────────────────────────────────────────────────

model_global = None


def main():
    global map_data, position_tracker, model_global, stt_engine, nav_queue_global

    print("=" * 55, flush=True)
    print("       SANA Smart Glasses – Booting", flush=True)
    if TEST_MODE:
        print("       *** TEST MODE – keyboard input ***", flush=True)
    print("=" * 55, flush=True)

    map_data = load_map(MAP_FILE)
    print(f"[MAIN] Map: {len(map_data['nodes'])} nodes | {len(map_data['rooms'])} rooms", flush=True)

    model_global = load_yolo_model(YOLO_MODEL_PATH)

    position_tracker = PositionTracker(
        start_node_id=ORIGIN_NODE,
        map_data=map_data,
    )
    position_tracker.start()
    print(f"[MAIN] Origin: Elevator N1 – facing north", flush=True)

    register_state_callbacks(
        get_node_fn    = lambda: position_tracker.current_node,
        get_heading_fn = lambda: position_tracker.get_heading_name(),
        nav_active_fn  = lambda: navigation_active.is_set(),
    )

    nav_queue: queue.Queue = queue.Queue()
    nav_queue_global = nav_queue

    register_nav_queue(nav_queue)
    register_action_callbacks(
        trigger_stt_fn  = lambda: (
            stt_engine._active_listen(trigger="app")
            if stt_engine and not stt_engine._active_listening else None
        ),
        announce_loc_fn = announce_location,
    )
    start_bridge()

    if TEST_MODE:
        threading.Thread(
            target=test_input_loop,
            args=(nav_queue,),
            daemon=True,
        ).start()
        speak_text_ar("وضع الاختبار، اكتب الوجهة")

    else:
        from sana_stt import STTEngine, stt_result_queue as real_stt_queue

        stt_engine = STTEngine(
            speak_callback  = speak_text_ar,
            pause_callback  = yolo_pause_event.set,
            resume_callback = yolo_pause_event.clear,
            map_data        = map_data,
        )

        def on_button_press():
            threading.Thread(target=handle_hold_touch, daemon=True).start()

        stt_engine._button.when_pressed = on_button_press

        try:
            stt_engine._button.bounce_time = 0.15
        except Exception:
            pass

        stt_engine.start()

        speak_text_ar(
            "مرحبا انا سَنَا. "
            "المس الزر حتى سماع اهتزاز لوجهة جديدة، "
            "المس الزر حتى سماع اهتزازين للموقع الحالي، "
            "المس الزر حتى سماع ثلاثة اهتزازات للاتصال بالطوارئ"
        )
        vibrate_pattern([0.1, 0.1, 0.1, 0.1, 0.1])

        def stt_bridge_loop():
            while not shutdown_event.is_set():
                try:
                    result = real_stt_queue.get(timeout=1)
                    nav_queue.put(result)
                except queue.Empty:
                    continue

        threading.Thread(target=stt_bridge_loop, daemon=True).start()

    print("[MAIN] Ready.", flush=True)

    try:
        while not shutdown_event.is_set():
            try:
                result = nav_queue.get(timeout=1)
            except queue.Empty:
                continue

            if result.get("type") == "navigation":
                handle_navigation_request(
                    result["text"],
                    result.get("english_room", ""),
                )
            elif result.get("type") == "get_location":
                threading.Thread(target=announce_location, daemon=True).start()
            elif result.get("type") == "interrupted":
                print("\n[NAV] Navigation stopped. Type new destination:", flush=True)

    except KeyboardInterrupt:
        print("\n[MAIN] Interrupted.", flush=True)

    finally:
        shutdown_event.set()
        vibration_motor.off()
        if not TEST_MODE:
            try:
                stt_engine.stop()
            except Exception:
                pass
        if position_tracker:
            position_tracker.stop()
        try:
            vibration_motor.close()
        except Exception:
            pass
        speak_text_ar("إلى اللقاء")
        print("[MAIN] Done.", flush=True)


if __name__ == "__main__":
    main()
