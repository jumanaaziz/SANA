#!/usr/bin/env python3
"""
test_yolo_ocr.py — Standalone YOLO + OCR Test
==============================================
Tests the exact same YOLO and OCR logic used in sana_main.py
but without navigation, STT, or position tracking.

What it does:
    - Opens live camera
    - Runs YOLO every frame
    - Detects obstacles → speaks Arabic warning
    - Detects signs → asks user (keyboard y/n) → runs OCR → speaks text
    - Prints all detections to terminal

Run:
    source ~/sana_venv/bin/activate
    cd /home/sana
    python3 test_yolo_ocr.py

Keys:
    q     = quit
    s     = save current frame to debug_outputs/
    o     = force OCR on current frame (no sign detection needed)
"""

import time
import threading
import sys

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
    YOLO_CONF_THRESHOLD,
    LIVE_EVERY_N_FRAMES,
    DEBUG_DIR,
)

import cv2

# ── CONFIG ────────────────────────────────────────────────────────────────────
SIGN_COOLDOWN_SEC = 10    # seconds before asking about same sign again
AUTO_SKIP_SIGN    = False  # True = auto OCR without asking, False = ask y/n

# ── GLOBALS ───────────────────────────────────────────────────────────────────
shutdown_event = threading.Event()


# ── SIGN HANDLER ──────────────────────────────────────────────────────────────

def handle_sign(frame, best_sign: dict):
    """
    Exact same logic as sana_main.py handle_sign
    but uses keyboard y/n instead of STT.
    """
    try:
        speak_text_ar("أرى لافتة أمامك، هل تريد قراءتها؟")

        if AUTO_SKIP_SIGN:
            print("[SIGN] Auto OCR mode — reading sign...", flush=True)
            answer = "y"
        else:
            print("[SIGN] Sign detected! Read it? (y/n): ", end="", flush=True)
            try:
                answer = input().strip().lower()
            except Exception:
                answer = "n"

        if answer in ["y", "yes", "نعم", "ايوه"]:
            print("[SIGN] Running OCR...", flush=True)
            cropped = crop_bbox(frame, best_sign["bbox"])
            process_sign_crop(cropped, int(time.time()))
        else:
            print("[SIGN] Skipped.", flush=True)
            speak_text_ar("حسناً")

    except Exception as e:
        print(f"[SIGN] Error: {e}", flush=True)


# ── MAIN LOOP ─────────────────────────────────────────────────────────────────

def main():
    print("=" * 50, flush=True)
    print("  SANA — YOLO + OCR Test", flush=True)
    print(f"  Model    : {YOLO_MODEL_PATH}", flush=True)
    print(f"  Conf     : {YOLO_CONF_THRESHOLD}", flush=True)
    print(f"  AutoOCR  : {AUTO_SKIP_SIGN}", flush=True)
    print("=" * 50, flush=True)
    print("Keys: q=quit  s=save frame  o=force OCR\n", flush=True)

    # Load YOLO model
    model = load_yolo_model(YOLO_MODEL_PATH)

    picam2       = None
    frame_count  = 0
    sign_cooldown = 0
    last_frame   = None

    try:
        picam2 = create_picamera2()
        print("[CAM] Camera started ✅", flush=True)
        speak_text_ar("كاميرا جاهزة، جاري الفحص")

        while not shutdown_event.is_set():
            # Capture frame
            rgb   = picam2.capture_array()
            frame = picamera2_frame_to_bgr(rgb)
            last_frame = frame
            frame_count += 1

            # Run YOLO every N frames
            if frame_count % max(1, LIVE_EVERY_N_FRAMES) != 0:
                time.sleep(0.01)
                continue

            # Detect objects
            detections = detect_objects(model, frame)

            if detections:
                # Print all detections
                print(f"[YOLO] Frame {frame_count} — {len(detections)} object(s):", flush=True)
                for d in detections:
                    print(f"         {d['class_name']:15s} conf={d['confidence']:.2f} bbox={d['bbox']}", flush=True)

                # Obstacle warnings (exact same as sana_main.py)
                process_obstacles(detections)

                # Sign detection (exact same logic)
                best_sign = choose_best_sign(detections)
                now = time.time()
                if best_sign and (now - sign_cooldown) > SIGN_COOLDOWN_SEC:
                    sign_cooldown = now
                    print(f"\n[SIGN] Sign detected! conf={best_sign['confidence']:.2f}", flush=True)
                    # Run in thread so camera keeps running
                    threading.Thread(
                        target=handle_sign,
                        args=(frame.copy(), best_sign),
                        daemon=True,
                    ).start()
            else:
                # Print "nothing" every 30 frames to show it's running
                if frame_count % 30 == 0:
                    print(f"[YOLO] Frame {frame_count} — no detections", flush=True)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[TEST] Interrupted.", flush=True)

    except Exception as e:
        print(f"[TEST] Error: {e}", flush=True)

    finally:
        if picam2:
            try:
                picam2.stop()
            except Exception:
                pass
        print("[TEST] Done.", flush=True)


if __name__ == "__main__":
    main()
