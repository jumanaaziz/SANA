#!/usr/bin/env python3
"""
Sana Smart Glasses - Raspberry Pi 5 LIVE YOLO + OCR + TTS Runtime

New in this version:
- Live CSI camera preview using Picamera2.
- Continuous YOLO detection on video frames.
- Press:
    q = quit live mode
    o = OCR/read current frame or current detected sign
    s = save current frame to debug_outputs
- Terminal commands:
    live
    read
    test /path/to/image.jpg
    quit

Notes:
- For live video, install Picamera2:
    sudo apt install -y python3-picamera2
- This version still supports still capture using rpicam-still for "read".
"""

from __future__ import annotations

import os
import sys
import cv2
import time
import queue
import shutil
import serial
import tempfile
import threading
import subprocess
from pathlib import Path
from typing import Optional, Any

import requests
import numpy as np
from deep_translator import GoogleTranslator
from ultralytics import YOLO

# =========================
# CONFIG
# =========================
OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "PUT_YOUR_OCR_SPACE_KEY_HERE")
YOLO_MODEL_PATH = os.getenv("SANA_YOLO_MODEL", "/home/sana/best.pt")

CAMERA_WIDTH = int(os.getenv("SANA_CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.getenv("SANA_CAMERA_HEIGHT", "480"))
CAMERA_TIMEOUT_MS = int(os.getenv("SANA_CAMERA_TIMEOUT", "1000"))
RPICAM_CMD = os.getenv("SANA_RPICAM_CMD", "rpicam-still")

SERIAL_PORT = os.getenv("SANA_SERIAL_PORT", "/dev/serial0")
SERIAL_BAUDRATE = int(os.getenv("SANA_SERIAL_BAUD", "115200"))
ENABLE_UART = os.getenv("SANA_ENABLE_UART", "1") == "1"

SIGN_CLASS_NAME = os.getenv("SANA_SIGN_CLASS", "sign")
YOLO_CONF_THRESHOLD = float(os.getenv("SANA_YOLO_CONF", "0.50"))
YOLO_IMGSZ = int(os.getenv("SANA_YOLO_IMGSZ", "320"))
OCR_LANGUAGE = os.getenv("SANA_OCR_LANGUAGE", "eng")
DUPLICATE_COOLDOWN_SEC = int(os.getenv("SANA_COOLDOWN", "8"))

# Live settings
LIVE_EVERY_N_FRAMES = int(os.getenv("SANA_LIVE_EVERY", "2"))  # run YOLO every N frames
LIVE_WINDOW_NAME = os.getenv("SANA_LIVE_WINDOW", "Sana Live YOLO")
LIVE_SPEAK_OBSTACLES = os.getenv("SANA_LIVE_SPEAK", "1") == "1"

DEBUG_DIR = Path(os.getenv("SANA_DEBUG_DIR", "/home/sana/debug_outputs"))
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

OBSTACLE_ARABIC = {
    "Chairs": "انتبه، يوجد كراسي أمامك",
    "chair": "انتبه، يوجد كرسي أمامك",
    "door": "انتبه، يوجد باب أمامك",
    "person": "انتبه، يوجد شخص أمامك",
    "stairs": "انتبه، يوجد درج أمامك",
    "table": "انتبه، يوجد طاولة أمامك",
}

ARROW_LABELS_AR = {
    "up": "للأمام",
    "down": "للخلف",
    "left": "لليسار",
    "right": "لليمين",
    "unknown": "اتجاه غير محدد",
}

# =========================
# GLOBALS
# =========================
command_queue: queue.Queue[tuple[str, Optional[str]]] = queue.Queue()
shutdown_event = threading.Event()
serial_lock = threading.Lock()
serial_conn: Optional[serial.Serial] = None
last_spoken_text = ""
last_spoken_time = 0.0

# =========================
# UART
# =========================
def open_serial_once() -> Optional[serial.Serial]:
    global serial_conn
    if not ENABLE_UART:
        return None
    if serial_conn is not None:
        return serial_conn
    try:
        serial_conn = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
        time.sleep(1)
        print(f"[INFO] UART opened on {SERIAL_PORT}", flush=True)
        return serial_conn
    except Exception as exc:
        print(f"[WARN] UART not available on {SERIAL_PORT}: {exc}", flush=True)
        serial_conn = None
        return None


def send_serial_message(message: str) -> None:
    ser = open_serial_once()
    if ser is None:
        return
    try:
        with serial_lock:
            ser.write((message.strip() + "\n").encode("utf-8"))
        print(f"[PI -> ESP32] {message}", flush=True)
    except Exception as exc:
        print(f"[WARN] UART send failed: {exc}", flush=True)


def serial_listener() -> None:
    ser = open_serial_once()
    if ser is None:
        return
    while not shutdown_event.is_set():
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            print(f"[ESP32 -> PI] {line}", flush=True)
            if line in {"TOUCH_PRESSED", "TOUCH_TRIGGER", "BUTTON_TRIGGER", "READ_SIGN"}:
                command_queue.put(("read", None))
            elif line in {"LIVE", "START_LIVE"}:
                command_queue.put(("live", None))
        except Exception as exc:
            print(f"[ERROR] UART listener error: {exc}", flush=True)
            time.sleep(1)

# =========================
# TTS + TRANSLATION
# =========================
_tts_busy = False

def speak_text_ar(text: str) -> None:
    global _tts_busy
    text = (text or "").strip()
    if not text:
        return
    print(f"[TTS-AR] {text}", flush=True)
    _tts_busy = True
    try:
        from gtts import gTTS
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            mp3_path = tmp.name
        gTTS(text=text, lang="ar").save(mp3_path)
        subprocess.run(["mpg123", "-q", mp3_path], check=False)
        os.unlink(mp3_path)
    except Exception as exc:
        print(f"[WARN] gTTS failed, fallback to espeak: {exc}", flush=True)
        subprocess.run(["espeak", "-v", "ar", text], check=False)
    finally:
        _tts_busy = False


def translate_to_arabic(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source="auto", target="ar").translate(text)
        return translated.strip() if translated else text
    except Exception as exc:
        print(f"[WARN] Translation failed: {exc}", flush=True)
        return text


def should_speak_text(text: str) -> bool:
    global last_spoken_text, last_spoken_time
    text = (text or "").strip()
    if not text:
        return False
    now = time.time()
    if text == last_spoken_text and (now - last_spoken_time) < DUPLICATE_COOLDOWN_SEC:
        return False
    last_spoken_text = text
    last_spoken_time = now
    return True

# =========================
# CAMERA
# =========================
def capture_frame() -> Optional[np.ndarray]:
    """Still capture using rpicam-still. Good for OCR/manual read."""
    if shutil.which(RPICAM_CMD) is None:
        print(f"[ERROR] Camera command not found: {RPICAM_CMD}", flush=True)
        print("[HINT] Install/test: sudo apt install -y rpicam-apps && rpicam-hello --list-cameras", flush=True)
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp_path = tmp.name
        cmd = [
            RPICAM_CMD,
            "-o", tmp_path,
            "--width", str(CAMERA_WIDTH),
            "--height", str(CAMERA_HEIGHT),
            "--nopreview",
            "-t", str(CAMERA_TIMEOUT_MS),
        ]
        print(f"[CAM] {' '.join(cmd)}", flush=True)
        completed = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if completed.returncode != 0:
            print(f"[ERROR] rpicam-still failed: {completed.returncode}", flush=True)
            print(completed.stderr.strip(), flush=True)
            return None
        frame = cv2.imread(tmp_path)
        if frame is None:
            print("[ERROR] Could not read captured image.", flush=True)
            return None
        print(f"[CAM] Captured frame: {frame.shape[1]}x{frame.shape[0]}", flush=True)
        return frame
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def load_test_image(path: str) -> Optional[np.ndarray]:
    frame = cv2.imread(path)
    if frame is None:
        print(f"[ERROR] Could not load image: {path}", flush=True)
        return None
    print(f"[INFO] Loaded test image: {path} ({frame.shape[1]}x{frame.shape[0]})", flush=True)
    return frame


def create_picamera2():
    try:
        from picamera2 import Picamera2
    except Exception as exc:
        raise RuntimeError(
            "Picamera2 is not installed. Install it with: sudo apt install -y python3-picamera2"
        ) from exc

    picam2 = Picamera2()
    config = picam2.create_video_configuration(
        main={"size": (CAMERA_WIDTH, CAMERA_HEIGHT), "format": "RGB888"}
    )
    picam2.configure(config)
    picam2.start()
    time.sleep(1)
    return picam2


def picamera2_frame_to_bgr(frame: np.ndarray) -> np.ndarray:
    if frame is None:
        return frame
    if len(frame.shape) == 3 and frame.shape[2] == 3:
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    if len(frame.shape) == 3 and frame.shape[2] == 4:
        return cv2.cvtColor(frame, cv2.COLOR_RGBA2BGR)
    return frame

# =========================
# YOLO
# =========================
def load_yolo_model(model_path: str) -> YOLO:
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"YOLO model not found: {model_path}")
    print(f"[INFO] Loading YOLO model: {model_path}", flush=True)
    model = YOLO(model_path)
    print(f"[INFO] YOLO classes: {model.names}", flush=True)
    return model


def detect_objects(model: YOLO, frame: np.ndarray) -> list[dict[str, Any]]:
    results = model.predict(frame, conf=YOLO_CONF_THRESHOLD, imgsz=YOLO_IMGSZ, verbose=False)
    if not results:
        return []
    result = results[0]
    if result.boxes is None:
        return []

    detections: list[dict[str, Any]] = []
    for box in result.boxes:
        cls_id = int(box.cls[0].item())
        conf = float(box.conf[0].item())
        class_name = str(model.names.get(cls_id, cls_id))
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int).tolist()
        detections.append({
            "class_name": class_name,
            "confidence": conf,
            "bbox": (x1, y1, x2, y2),
        })
    return detections


def draw_detections(frame: np.ndarray, detections: list[dict[str, Any]]) -> np.ndarray:
    out = frame.copy()
    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        label = f"{det['class_name']} {det['confidence']:.2f}"
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
    cv2.putText(out, "q: quit | o: OCR | s: save", (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    return out

# =========================
# OCR + SIGN PROCESSING
# =========================
def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w < 900:
        scale = 900 / max(w, 1)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)
    return cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 11,
    )


def clean_ocr_text(text: str) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return " ".join(" ".join(lines).split())


def run_ocr_space(image: np.ndarray) -> str:
    if OCR_SPACE_API_KEY == "PUT_YOUR_OCR_SPACE_KEY_HERE":
        print("[ERROR] OCR_SPACE_API_KEY is not set.", flush=True)
        return ""
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        print("[ERROR] Failed to encode OCR image.", flush=True)
        return ""
    files = {"filename": ("sign.jpg", encoded.tobytes(), "image/jpeg")}
    payload = {
        "apikey": OCR_SPACE_API_KEY,
        "language": OCR_LANGUAGE,
        "isOverlayRequired": False,
        "OCREngine": 2,
        "scale": True,
    }
    try:
        response = requests.post("https://api.ocr.space/parse/image", files=files, data=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        if data.get("IsErroredOnProcessing"):
            print(f"[ERROR] OCR error: {data.get('ErrorMessage')}", flush=True)
            return ""
        parsed = data.get("ParsedResults", [])
        if not parsed:
            return ""
        return clean_ocr_text(parsed[0].get("ParsedText", ""))
    except Exception as exc:
        print(f"[ERROR] OCR request failed: {exc}", flush=True)
        return ""


def detect_arrow_direction(region: np.ndarray) -> str:
    if region is None or region.size == 0:
        return "unknown"
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "unknown"
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 100:
        return "unknown"
    x, y, w, h = cv2.boundingRect(largest)
    moments = cv2.moments(largest)
    if moments["m00"] == 0:
        return "unknown"
    cx = int(moments["m10"] / moments["m00"])
    cy = int(moments["m01"] / moments["m00"])
    dx = cx - (x + w // 2)
    dy = cy - (y + h // 2)
    if abs(dy) >= abs(dx):
        return "up" if dy < 0 else "down"
    return "left" if dx < 0 else "right"


def detect_all_row_arrows(sign_crop: np.ndarray, num_rows: int) -> list[str]:
    h, w = sign_crop.shape[:2]
    row_h = max(h // max(num_rows, 1), 1)
    directions = []
    for i in range(num_rows):
        y1 = i * row_h
        y2 = (i + 1) * row_h if i < num_rows - 1 else h
        row = sign_crop[y1:y2, :]
        third = max(row.shape[1] // 3, 1)
        arrow_zone = row[:, third: 2 * third]
        directions.append(detect_arrow_direction(arrow_zone))
    return directions


def crop_bbox(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return frame[y1:y2, x1:x2]


def choose_best_sign(detections: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    signs = [d for d in detections if d["class_name"] == SIGN_CLASS_NAME]
    return max(signs, key=lambda d: d["confidence"]) if signs else None


def process_sign_crop(sign_crop: np.ndarray, timestamp: int) -> None:
    if sign_crop is None or sign_crop.size == 0:
        speak_text_ar("لم أستطع قراءة اللافتة")
        send_serial_message("OCR_FAIL")
        return

    cv2.imwrite(str(DEBUG_DIR / f"sign_crop_{timestamp}.jpg"), sign_crop)
    h, w = sign_crop.shape[:2]
    aspect = w / max(h, 1)
    num_rows = 1 if aspect > 3.0 else 2 if aspect > 1.5 else 3
    arrows = detect_all_row_arrows(sign_crop, num_rows)
    print(f"[ARROWS] {arrows}", flush=True)

    processed = preprocess_for_ocr(sign_crop)
    cv2.imwrite(str(DEBUG_DIR / f"sign_processed_{timestamp}.jpg"), processed)
    raw_text = run_ocr_space(processed)
    print(f"[OCR RAW] {raw_text}", flush=True)

    if not raw_text:
        speak_text_ar("لم يتم العثور على نص في الصورة")
        send_serial_message("OCR_EMPTY")
        return

    translated = translate_to_arabic(raw_text)
    if arrows and arrows[0] != "unknown":
        speech = f"{translated}، الاتجاه {ARROW_LABELS_AR.get(arrows[0], 'غير محدد')}"
    else:
        speech = translated
    print(f"[SPEECH] {speech}", flush=True)
    if should_speak_text(speech):
        send_serial_message("OCR_OK")
        speak_text_ar(speech)


def process_obstacles(detections: list[dict[str, Any]]) -> None:
    spoken = set()
    for det in sorted(detections, key=lambda d: d["confidence"], reverse=True):
        cls = det["class_name"]
        if cls == SIGN_CLASS_NAME or cls in spoken:
            continue
        spoken.add(cls)
        warning = OBSTACLE_ARABIC.get(cls, "انتبه، يوجد عائق أمامك")
        print(f"[OBSTACLE] {cls} -> {warning}", flush=True)
        if should_speak_text(warning):
            send_serial_message("OBSTACLE")
            speak_text_ar(warning)


def process_frame(frame: np.ndarray, model: YOLO, allow_ocr_if_sign: bool = True) -> list[dict[str, Any]]:
    timestamp = int(time.time())
    cv2.imwrite(str(DEBUG_DIR / f"frame_{timestamp}.jpg"), frame)

    detections = detect_objects(model, frame)
    if not detections:
        print("[INFO] No objects detected.", flush=True)
        send_serial_message("NO_DETECTION")
        return []

    process_obstacles(detections)
    best_sign = choose_best_sign(detections)
    if allow_ocr_if_sign and best_sign:
        print(f"[INFO] Sign detected conf={best_sign['confidence']:.2f}", flush=True)
        process_sign_crop(crop_bbox(frame, best_sign["bbox"]), timestamp)
    return detections


def process_read(model: YOLO) -> None:
    print("[INFO] Capturing from camera...", flush=True)
    frame = capture_frame()
    if frame is None:
        speak_text_ar("خطأ في الكاميرا")
        send_serial_message("CAMERA_FAIL")
        return
    process_frame(frame, model)


def process_test_image(path: str, model: YOLO) -> None:
    frame = load_test_image(path)
    if frame is not None:
        process_frame(frame, model)

# =========================
# LIVE MODE
# =========================
def live_camera_loop(model: YOLO) -> None:
    print("[INFO] Starting live camera mode.", flush=True)
    print("[INFO] Keys: q=quit, o=OCR current frame/sign, s=save frame", flush=True)

    picam2 = None
    last_detections: list[dict[str, Any]] = []
    last_frame: Optional[np.ndarray] = None
    frame_count = 0

    try:
        picam2 = create_picamera2()
        cv2.namedWindow(LIVE_WINDOW_NAME, cv2.WINDOW_NORMAL)

        while not shutdown_event.is_set():
            rgb = picam2.capture_array()
            frame = picamera2_frame_to_bgr(rgb)
            last_frame = frame

            if frame_count % max(1, LIVE_EVERY_N_FRAMES) == 0:
                last_detections = detect_objects(model, frame)
                if LIVE_SPEAK_OBSTACLES and last_detections:
                    process_obstacles(last_detections)

            display = draw_detections(frame, last_detections)
            cv2.imshow(LIVE_WINDOW_NAME, display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord("s") and last_frame is not None:
                path = DEBUG_DIR / f"live_frame_{int(time.time())}.jpg"
                cv2.imwrite(str(path), last_frame)
                print(f"[SAVE] {path}", flush=True)
            elif key == ord("o") and last_frame is not None:
                timestamp = int(time.time())
                best_sign = choose_best_sign(last_detections)
                if best_sign:
                    process_sign_crop(crop_bbox(last_frame, best_sign["bbox"]), timestamp)
                else:
                    process_sign_crop(last_frame, timestamp)

            frame_count += 1

    except Exception as exc:
        print(f"[ERROR] Live camera failed: {exc}", flush=True)
        print("[HINT] Install Picamera2: sudo apt install -y python3-picamera2", flush=True)
    finally:
        if picam2 is not None:
            try:
                picam2.stop()
            except Exception:
                pass
        cv2.destroyAllWindows()
        print("[INFO] Live mode stopped.", flush=True)

# =========================
# COMMANDS
# =========================
def manual_command_listener() -> None:
    while not shutdown_event.is_set():
        try:
            cmd = input("Command (live / read / test <image_path> / quit): ").strip()
        except EOFError:
            return
        if cmd == "live":
            command_queue.put(("live", None))
        elif cmd == "read":
            command_queue.put(("read", None))
        elif cmd.startswith("test "):
            path = cmd[5:].strip()
            if os.path.exists(path):
                command_queue.put(("test", path))
            else:
                print(f"[ERROR] File not found: {path}", flush=True)
        elif cmd == "quit":
            command_queue.put(("quit", None))
            return
        elif cmd:
            print("Unknown command. Use: live / read / test <image_path> / quit", flush=True)


def main() -> None:
    print("[INFO] Sana Pi5 LIVE YOLO + OCR runtime starting...", flush=True)
    print(f"[INFO] Model path: {YOLO_MODEL_PATH}", flush=True)
    print(f"[INFO] imgsz={YOLO_IMGSZ}, conf={YOLO_CONF_THRESHOLD}", flush=True)

    model = load_yolo_model(YOLO_MODEL_PATH)

    if ENABLE_UART:
        threading.Thread(target=serial_listener, daemon=True).start()
    threading.Thread(target=manual_command_listener, daemon=True).start()

    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        command_queue.put(("test", sys.argv[1]))

    while not shutdown_event.is_set():
        try:
            cmd, payload = command_queue.get(timeout=1)
        except queue.Empty:
            continue
        if cmd == "live":
            live_camera_loop(model)
        elif cmd == "read":
            process_read(model)
        elif cmd == "test":
            process_test_image(payload or "", model)
        elif cmd == "quit":
            shutdown_event.set()
            break

    if serial_conn is not None:
        try:
            serial_conn.close()
        except Exception:
            pass
    print("[INFO] Stopped.", flush=True)


if __name__ == "__main__":
    main()
