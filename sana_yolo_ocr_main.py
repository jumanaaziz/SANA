"""Sana OCR controller for Raspberry Pi Zero 2 W.

Flow:
- Wait for either:
  1) Touch event from ESP32 over UART
  2) Simple user command from terminal (for testing before STT is added)
  3) Local image upload path (for offline testing without camera)
- Capture a frame from the USB camera (or load test image)
- Run YOLO to detect: Chairs, door, person, sign, stairs, table
- For non-sign obstacles: speak Arabic warning directly
- For sign: crop → detect arrow direction visually → OCR text → speak combined result
- Optionally notify ESP32

Dependencies:
    pip install requests opencv-python pillow pyserial deep-translator ultralytics gtts playsound

System packages for TTS on Raspberry Pi:
    sudo apt update
    sudo apt install -y espeak ffmpeg
"""

import os
import sys
import cv2
import time
import queue
import threading
import subprocess
import platform
import requests
import numpy as np
import serial
from deep_translator import GoogleTranslator
from ultralytics import YOLO

# =========================
# CONFIG
# =========================
OCR_SPACE_API_KEY = "K87107613888957"
YOLO_MODEL_PATH = os.getenv("SANA_YOLO_MODEL", "best (6).pt")

CAMERA_INDEX = 0

SERIAL_PORT = "/dev/serial0"
SERIAL_BAUDRATE = 115200

SIGN_CLASS_NAME = "sign"
YOLO_CONF_THRESHOLD = 0.50

OCR_LANGUAGE = "eng"

DUPLICATE_TEXT_COOLDOWN_SEC = 8

DEBUG_DIR = "debug_outputs"
os.makedirs(DEBUG_DIR, exist_ok=True)

# Detect if running on Raspberry Pi
IS_RASPBERRY_PI = platform.machine().startswith("aarch") or platform.machine() == "armv7l"

# =========================
# OBSTACLE ARABIC LABELS
# =========================
OBSTACLE_ARABIC = {
    "Chairs": "انتبه، يوجد كراسي أمامك",
    "door":   "انتبه، يوجد باب أمامك",
    "person": "انتبه، يوجد شخص أمامك",
    "stairs": "انتبه، يوجد درج أمامك",
    "table":  "انتبه، يوجد طاولة أمامك",
}

# =========================
# ARROW DIRECTION DETECTION
# =========================

ARROW_LABELS_AR = {
    "up":    "للأمام",
    "down":  "للخلف",
    "left":  "لليسار",
    "right": "لليمين",
    "unknown": "اتجاه غير محدد",
}


def detect_arrow_direction(arrow_region: np.ndarray) -> str:
    """
    Detect arrow direction from a cropped image region (the middle column of the sign).
    Uses contour + bounding-box centroid approach:
    - Convert to grayscale, threshold to isolate dark arrow on light/teal background
    - Find largest contour (the arrow shape)
    - Compute moments to find centroid
    - Compare centroid vs bounding-box center to infer direction

    Returns: 'up', 'down', 'left', 'right', or 'unknown'
    """
    if arrow_region is None or arrow_region.size == 0:
        return "unknown"

    gray = cv2.cvtColor(arrow_region, cv2.COLOR_BGR2GRAY)

    # Threshold: arrows are dark on lighter background
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return "unknown"

    # Largest contour = arrow body
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 100:
        return "unknown"

    x, y, w, h = cv2.boundingRect(largest)
    M = cv2.moments(largest)
    if M["m00"] == 0:
        return "unknown"

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    # Center of bounding box
    box_cx = x + w // 2
    box_cy = y + h // 2

    # Offset of centroid relative to bounding box center
    dx = cx - box_cx
    dy = cy - box_cy

    # Decide direction based on larger axis offset
    if abs(dy) >= abs(dx):
        # Vertical arrow
        if dy < 0:
            return "up"
        else:
            return "down"
    else:
        # Horizontal arrow
        if dx < 0:
            return "left"
        else:
            return "right"


def extract_arrow_region(sign_crop: np.ndarray) -> np.ndarray:
    """
    Extract the middle column (arrow zone) from the sign crop.
    We split horizontally into thirds: left-text | arrow | right-text
    """
    h, w = sign_crop.shape[:2]
    third = w // 3
    arrow_region = sign_crop[:, third: 2 * third]
    return arrow_region


def detect_all_row_arrows(sign_crop: np.ndarray, num_rows: int) -> list[str]:
    """
    Split sign_crop into num_rows horizontal bands, then detect arrow per row.
    Returns list of direction strings.
    """
    h, w = sign_crop.shape[:2]
    row_h = h // max(num_rows, 1)
    directions = []
    for i in range(num_rows):
        y1 = i * row_h
        y2 = (i + 1) * row_h if i < num_rows - 1 else h
        row = sign_crop[y1:y2, :]
        arrow_zone = extract_arrow_region(row)
        direction = detect_arrow_direction(arrow_zone)
        directions.append(direction)
    return directions


# =========================
# SIGN TEXT PARSING
# =========================

def parse_sign_rows_from_ocr(raw_text: str) -> list[str]:
    """
    OCR returns a flat string. We split into lines and pair them.
    Each real row on the sign will appear as one or two lines in OCR
    (English label + Arabic label, arrow is graphical so not in OCR).

    Strategy:
    - Split by newlines
    - Filter empty lines
    - Each logical row = one or two consecutive lines
    Returns list of cleaned row texts.
    """
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    return lines


def build_sign_speech(ocr_lines: list[str], arrow_directions: list[str]) -> str:
    """
    Combine OCR text lines with detected arrow directions into Arabic speech.

    If we have multiple rows detected, we pair them.
    For single-line signs (just a room number etc), speak it directly.
    """
    if not ocr_lines:
        return "لم يتم قراءة النص"

    parts = []

    # Try to pair lines with arrows
    # heuristic: if more arrows than lines, ignore extras; vice versa
    for i, line in enumerate(ocr_lines):
        direction = arrow_directions[i] if i < len(arrow_directions) else "unknown"
        direction_ar = ARROW_LABELS_AR.get(direction, "")

        # Translate English parts to Arabic if needed
        translated = translate_to_arabic(line)
        text_to_say = translated if translated else line

        if direction_ar and direction != "unknown":
            parts.append(f"{text_to_say}، اتجاه {direction_ar}")
        else:
            parts.append(text_to_say)

    return "... ".join(parts)


# =========================
# GLOBAL STATE
# =========================
last_spoken_text = ""
last_spoken_time = 0
command_queue = queue.Queue()


def translate_to_arabic(text: str) -> str:
    if not text.strip():
        return ""
    try:
        translated = GoogleTranslator(source="auto", target="ar").translate(text)
        return translated.strip() if translated else ""
    except Exception as e:
        print(f"[WARN] Translation failed: {e}")
        return text


# =========================
# TTS
# =========================

def speak_text_ar(text: str):
    """
    Speak Arabic text.
    - On Raspberry Pi: use espeak -v ar
    - On other platforms: use gTTS (saves temp mp3, plays it)
    """
    if not text.strip():
        return

    print(f"[TTS-AR] {text}")

    if IS_RASPBERRY_PI:
        _speak_espeak(text)
    else:
        _speak_gtts(text)


def _speak_espeak(text: str):
    try:
        subprocess.run(["espeak", "-v", "ar", text], check=False)
    except Exception as e:
        print(f"[ERROR] espeak TTS failed: {e}")


def _speak_gtts(text: str):
    try:
        from gtts import gTTS
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        tts = gTTS(text=text, lang="ar")
        tts.save(tmp_path)

        # Try different players depending on OS
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["afplay", tmp_path], check=False)
        elif system == "Windows":
         from playsound import playsound
         playsound(tmp_path)
        else:
            # Linux desktop
            subprocess.run(["mpg123", tmp_path], check=False)

        os.unlink(tmp_path)

    except Exception as e:
        print(f"[ERROR] gTTS failed: {e}")
        print(f"[TTS FALLBACK] Text was: {text}")


# =========================
# IMAGE PREPROCESSING FOR OCR
# =========================

def preprocess_for_ocr(image: np.ndarray) -> np.ndarray:
    if image is None or image.size == 0:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    h, w = gray.shape[:2]
    if w < 800:
        scale = 800 / max(w, 1)
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)

    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        31, 11
    )

    return thresh


# =========================
# OCR  (DO NOT MODIFY)
# =========================

def run_ocr_space(image: np.ndarray) -> str:
   

    success, encoded = cv2.imencode(".jpg", image)
    if not success:
        print("[ERROR] Failed to encode OCR image.")
        return ""

    files = {"filename": ("sign.jpg", encoded.tobytes(), "image/jpeg")}
    payload = {
        "apikey": OCR_SPACE_API_KEY,
        "language": OCR_LANGUAGE,
        "isOverlayRequired": False,
        "OCREngine": 2,
        "scale": True
    }

    try:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files=files,
            data=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()

        parsed_results = data.get("ParsedResults", [])
        if not parsed_results:
            return ""

        text = parsed_results[0].get("ParsedText", "")
        return clean_ocr_text(text)

    except Exception as e:
        print(f"[ERROR] OCR request failed: {e}")
        return ""


def clean_ocr_text(text: str) -> str:
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = " ".join(lines)
    cleaned = " ".join(cleaned.split())
    return cleaned


# =========================
# CAMERA
# =========================

def capture_frame(camera_index: int = CAMERA_INDEX) -> np.ndarray | None:
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        return None

    for _ in range(5):
        cap.read()
        time.sleep(0.05)

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print("[ERROR] Failed to capture frame.")
        return None

    return frame


def load_test_image(path: str) -> np.ndarray | None:
    """Load a local image file for testing instead of camera."""
    frame = cv2.imread(path)
    if frame is None:
        print(f"[ERROR] Could not load image: {path}")
        return None
    frame = cv2.cvtColor(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), cv2.COLOR_RGB2BGR)
    print(f"[INFO] Loaded test image: {path} ({frame.shape[1]}x{frame.shape[0]})")
    return frame


# =========================
# YOLO
# =========================

def load_yolo_model(model_path: str) -> YOLO:
    print(f"[INFO] Loading YOLO model from: {model_path}")
    model = YOLO(model_path)
    return model


def detect_objects(model: YOLO, frame: np.ndarray) -> list[dict]:
    """
    Run YOLO and return ALL detections (not just signs).
    """
    results = model.predict(frame, conf=0.01, verbose=True)

    if not results or len(results) == 0:
        return []

    result = results[0]
    boxes = result.boxes
    if boxes is None:
        return []

    detections = []
    for box in boxes:
        cls_id = int(box.cls[0].item())
        conf = float(box.conf[0].item())
        class_name = model.names[cls_id]
        xyxy = box.xyxy[0].cpu().numpy().astype(int)
        x1, y1, x2, y2 = xyxy.tolist()

        print(f"[YOLO] class={class_name}, conf={conf:.2f}, bbox=({x1},{y1},{x2},{y2})")

        detections.append({
            "class_name": class_name,
            "confidence": conf,
            "bbox": (x1, y1, x2, y2)
        })

    return detections


def choose_best_sign(detections: list[dict]) -> dict | None:
    signs = [d for d in detections if d["class_name"] == SIGN_CLASS_NAME]
    if not signs:
        return None
    return max(signs, key=lambda d: d["confidence"])


def get_obstacle_detections(detections: list[dict]) -> list[dict]:
    return [d for d in detections if d["class_name"] != SIGN_CLASS_NAME]


def crop_bbox(frame: np.ndarray, bbox: tuple) -> np.ndarray:
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = bbox
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    return frame[y1:y2, x1:x2]


# =========================
# DUPLICATE FILTER
# =========================

def should_speak_text(text: str) -> bool:
    global last_spoken_text, last_spoken_time

    if not text:
        return False

    now = time.time()
    if text == last_spoken_text and (now - last_spoken_time) < DUPLICATE_TEXT_COOLDOWN_SEC:
        print("[INFO] Duplicate text ignored.")
        return False

    last_spoken_text = text
    last_spoken_time = now
    return True


# =========================
# SERIAL COMMUNICATION
# =========================

def serial_listener():
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
        print(f"[INFO] Serial listener started on {SERIAL_PORT}")
    except Exception as e:
        print(f"[ERROR] Could not open serial port: {e}")
        return

    while True:
        try:
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                print(f"[ESP32 -> PI] {line}")
                if line == "TOUCH_PRESSED":
                    command_queue.put("read_sign")
        except Exception as e:
            print(f"[ERROR] Serial read failed: {e}")
            time.sleep(1)


def send_serial_message(message: str):
    try:
        ser = serial.Serial(SERIAL_PORT, SERIAL_BAUDRATE, timeout=1)
        ser.write((message + "\n").encode())
        ser.close()
        print(f"[PI -> ESP32] {message}")
    except Exception as e:
        print(f"[WARN] Could not send serial message: {e}")


# =========================
# MANUAL COMMAND THREAD
# =========================

def manual_command_listener():
    """
    Terminal commands:
      read           - capture from camera and process
      test <path>    - load local image for testing
      quit           - exit
    """
    while True:
        cmd = input("Command (read / test <image_path> / quit): ").strip().lower()

        if cmd == "read":
            command_queue.put(("read_sign", None))
        elif cmd.startswith("test "):
            path = cmd[5:].strip()
            if os.path.exists(path):
                command_queue.put(("test_image", path))
            else:
                print(f"[ERROR] File not found: {path}")
        elif cmd == "quit":
            command_queue.put(("quit", None))
            break
        else:
            print("Unknown command. Use: read / test <path> / quit")


# =========================
# SIGN PROCESSING FLOW
# =========================

def process_sign(frame: np.ndarray, sign_detection: dict, timestamp: int):
    """
    Full sign pipeline:
    1. Crop sign
    2. Detect arrow directions per row (visually)
    3. OCR the sign crop
    4. Parse OCR lines
    5. Build Arabic speech combining text + arrows
    6. Speak
    """
    bbox = sign_detection["bbox"]
    sign_crop = crop_bbox(frame, bbox)

    if sign_crop is None or sign_crop.size == 0:
        print("[ERROR] Empty sign crop.")
        speak_text_ar("لم أستطع قراءة اللافتة")
        send_serial_message("OCR_FAIL")
        return

    crop_path = os.path.join(DEBUG_DIR, f"sign_crop_{timestamp}.jpg")
    cv2.imwrite(crop_path, sign_crop)
    print(f"[DEBUG] Sign crop saved: {crop_path}")

    # --- Step 1: Detect rows in sign ---
    # Estimate number of rows by aspect ratio heuristic
    h, w = sign_crop.shape[:2]
    aspect = w / max(h, 1)

    if aspect > 3.0:
        # Very wide → likely single row
        num_rows = 1
    elif aspect > 1.5:
        num_rows = 2
    else:
        num_rows = 3

    print(f"[INFO] Estimated rows: {num_rows} (aspect={aspect:.2f})")

    # --- Step 2: Detect arrow directions ---
    arrow_directions = detect_all_row_arrows(sign_crop, num_rows)
    print(f"[ARROWS] Detected directions: {arrow_directions}")

    # Save arrow debug regions
    row_h = h // max(num_rows, 1)
    for i, direction in enumerate(arrow_directions):
        y1 = i * row_h
        y2 = (i + 1) * row_h if i < num_rows - 1 else h
        row = sign_crop[y1:y2, :]
        arrow_zone = extract_arrow_region(row)
        debug_path = os.path.join(DEBUG_DIR, f"arrow_row{i}_{timestamp}.jpg")
        cv2.imwrite(debug_path, arrow_zone)

    # --- Step 3: OCR ---
    processed = preprocess_for_ocr(sign_crop)
    proc_path = os.path.join(DEBUG_DIR, f"sign_processed_{timestamp}.jpg")
    cv2.imwrite(proc_path, processed)

    raw_text = run_ocr_space(processed)
    print(f"[OCR RAW] {raw_text}")

    if not raw_text:
        speak_text_ar("لم يتم العثور على نص في اللافتة")
        send_serial_message("OCR_EMPTY")
        return

    # --- Step 4: Parse OCR lines ---
    ocr_lines = parse_sign_rows_from_ocr(raw_text)
    print(f"[OCR LINES] {ocr_lines}")

    # --- Step 5: Build speech ---
    speech = build_sign_speech(ocr_lines, arrow_directions)
    print(f"[SPEECH] {speech}")

    # --- Step 6: Speak ---
    if should_speak_text(speech):
        speak_text_ar(speech)
        send_serial_message("OCR_OK")
    else:
        send_serial_message("OCR_DUPLICATE")


# =========================
# OBSTACLE SPEECH
# =========================

def process_obstacles(obstacle_detections: list[dict]):
    """
    For each non-sign obstacle detected, speak its Arabic warning.
    Deduplicated within cooldown window.
    """
    spoken_classes = set()

    # Sort by confidence descending, speak most confident first
    sorted_obs = sorted(obstacle_detections, key=lambda d: d["confidence"], reverse=True)

    for det in sorted_obs:
        cls = det["class_name"]
        if cls in spoken_classes:
            continue
        spoken_classes.add(cls)

        warning = OBSTACLE_ARABIC.get(cls, f"انتبه، يوجد عائق أمامك")
        print(f"[OBSTACLE] {cls} -> {warning}")

        if should_speak_text(warning):
            speak_text_ar(warning)


# =========================
# MAIN PROCESSING FLOW
# =========================

def process_frame(frame: np.ndarray, model: YOLO):
    """
    Given a frame (from camera or test image):
    1. Run YOLO on full frame
    2. Speak obstacle warnings for non-sign detections
    3. Process best sign detection if present
    """
    timestamp = int(time.time())

    raw_path = os.path.join(DEBUG_DIR, f"frame_{timestamp}.jpg")
    cv2.imwrite(raw_path, frame)

    detections = detect_objects(model, frame)

    if not detections:
        print("[INFO] No objects detected.")
        speak_text_ar("لم يتم اكتشاف أي عوائق")
        send_serial_message("NO_DETECTION")
        return

    # Handle obstacles first
    obstacles = get_obstacle_detections(detections)
    if obstacles:
        process_obstacles(obstacles)

    # Handle sign
    best_sign = choose_best_sign(detections)
    if best_sign:
        print(f"[INFO] Sign detected with conf={best_sign['confidence']:.2f}")
        process_sign(frame, best_sign, timestamp)
    elif not obstacles:
        speak_text_ar("لم يتم اكتشاف أي شيء")
        send_serial_message("NO_DETECTION")


def process_read_sign(model: YOLO):
    """Capture from camera and process."""
    print("[INFO] Capturing from camera...")
    frame = capture_frame()
    if frame is None:
        speak_text_ar("خطأ في الكاميرا")
        send_serial_message("OCR_FAIL")
        return
    process_frame(frame, model)


def process_test_image(path: str, model: YOLO):
    """Load local image and process (for testing without camera)."""
    print(f"[INFO] Loading test image: {path}")
    frame = load_test_image(path)
    if frame is None:
        print("[ERROR] Could not load test image.")
        return
    process_frame(frame, model)


# =========================
# MAIN
# =========================

def main():
    print("[INFO] Sana YOLO + OCR starting...")
    print(f"[INFO] Platform: {'Raspberry Pi' if IS_RASPBERRY_PI else platform.system()}")

    model = load_yolo_model(YOLO_MODEL_PATH)

    # Start UART listener from ESP32 (only on Pi)
    if IS_RASPBERRY_PI:
        serial_thread = threading.Thread(target=serial_listener, daemon=True)
        serial_thread.start()

    # Start terminal command listener
    manual_thread = threading.Thread(target=manual_command_listener, daemon=True)
    manual_thread.start()

    # If a test image is passed as CLI argument, run it directly
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        if os.path.exists(test_path):
            print(f"[INFO] CLI test mode: {test_path}")
            process_test_image(test_path, model)
        else:
            print(f"[ERROR] File not found: {test_path}")

    while True:
        try:
            cmd_tuple = command_queue.get(timeout=1)
        except queue.Empty:
            continue

        cmd, payload = cmd_tuple

        if cmd == "read_sign":
            process_read_sign(model)
        elif cmd == "test_image":
            process_test_image(payload, model)
        elif cmd == "quit":
            print("[INFO] Exiting.")
            break


if __name__ == "__main__":
    main()