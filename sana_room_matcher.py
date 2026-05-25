#!/usr/bin/env python3
"""
sana_room_matcher.py — Arabic Speech → Exact map.json Room Name
================================================================
Matches what user says to EXACT room name in map.json including numbers.

map.json room names:
    Classroom 44, Classroom 43, Classroom 42, Classroom 29, Classroom 28,
    Classroom 26, Classroom 18, Classroom 17, Classroom 8, Classroom 4,
    Classroom 3, Classroom 2
    Lab 41, Lab 40, Lab 39 A, Lab 39 B, Lab 32, Lab 30, Lab 25,
    Lab 23 A, Lab 23 B, Lab 22 A, Lab 22 B, Lab 20, Lab 16,
    Lab 14 A, Lab 14 B, Lab 7, Lab 5
    Office 45, Office 31, Office 27, Office 24, Office 21, Office 15,
    Office 13 A, Office 13 B, Office 6
    Bathroom (x3)
    IT Unit 38, IT Unit 10
    GP Experiment Room 9
"""

import re

# ── ROOM TYPE KEYWORDS ────────────────────────────────────────────────────────
ROOM_TYPE_MAP = [
    (["قاعة دراسية", "قاعة", "فصل", "كلاس"], "Classroom"),
    (["مختبر", "معمل", "لاب"],                "Lab"),
    (["مكتب", "أوفيس"],                       "Office"),
    (["حمام", "دورة مياه", "مرحاض"],          "Bathroom"),
    (["وحدة تقنية", "تقنية المعلومات"],       "IT Unit"),
    (["غرفة مشروع", "مشروع تخرج", "gp"],     "GP Experiment Room"),
]

# ── ARABIC NUMBER WORDS → DIGITS ──────────────────────────────────────────────
ONES = {
    "صفر": 0, "واحد": 1, "اثنين": 2, "اثنان": 2, "ثلاثة": 3,
    "أربعة": 4, "اربعة": 4, "خمسة": 5, "ستة": 6, "سبعة": 7,
    "ثمانية": 8, "تسعة": 9, "عشرة": 10, "أحد عشر": 11,
    "اثنا عشر": 12, "ثلاثة عشر": 13, "أربعة عشر": 14,
    "خمسة عشر": 15, "ستة عشر": 16, "سبعة عشر": 17,
    "ثمانية عشر": 18, "تسعة عشر": 19,
}
TENS = {
    "عشرين": 20, "ثلاثين": 30, "أربعين": 40, "اربعين": 40,
    "خمسين": 50, "ستين": 60, "سبعين": 70, "ثمانين": 80, "تسعين": 90,
}

# Build compound: "أربعة وأربعين" → 44
COMPOUND = {}
for o_word, o_val in ONES.items():
    if o_val == 0:
        continue
    for t_word, t_val in TENS.items():
        for sep in [f" و{t_word}", f" و {t_word}"]:
            COMPOUND[f"{o_word}{sep}"] = t_val + o_val

# Merge: compound first (longest match wins)
ALL_NUMBERS = {}
ALL_NUMBERS.update(COMPOUND)
ALL_NUMBERS.update(TENS)
ALL_NUMBERS.update(ONES)


def _extract_number(text: str) -> str:
    """Extract room number from spoken text."""
    # 1. Western digits
    hits = re.findall(r'\d+', text)
    if hits:
        return hits[0]

    # 2. Arabic-Indic ٠١٢٣٤٥٦٧٨٩
    indic = re.findall(r'[٠-٩]+', text)
    if indic:
        return indic[0].translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))

    # 3. Arabic number words (compound first)
    for word, val in ALL_NUMBERS.items():
        if word in text:
            return str(val)

    return ""


def _extract_type(text: str) -> str:
    """Extract English room type from Arabic text."""
    for keywords, eng in ROOM_TYPE_MAP:
        for kw in keywords:
            if kw in text:
                return eng
    return ""


def _suffix_score(text: str, room_name: str) -> int:
    """Bonus score for A/B suffix match."""
    has_a = "أ" in text or " a" in text.lower() or "ألف" in text
    has_b = "ب" in text or " b" in text.lower() or "باء" in text
    ends_a = room_name.endswith(" A")
    ends_b = room_name.endswith(" B")

    if has_a and ends_a:
        return 20
    if has_b and ends_b:
        return 20
    if has_a and ends_b:
        return -20
    if has_b and ends_a:
        return -20
    return 0


def arabic_to_room_name(arabic_text: str, map_data: dict) -> str:
    """
    Convert Arabic spoken text to exact room name in map.json.

    Examples:
        "القاعة الدراسية أربعة وأربعين" → "Classroom 44"
        "المختبر 39 أ"                  → "Lab 39 A"
        "الحمام"                         → "Bathroom"
        "مكتب خمسة وأربعين"             → "Office 45"
        "وحدة تقنية 38"                 → "IT Unit 38"
    """
    text  = arabic_text.strip()
    rooms = map_data.get("rooms", [])

    # ── 1. Direct fuzzy match (English words in speech) ──────────────────────
    tl = text.lower()
    for room in rooms:
        rl = room["name"].lower()
        if rl in tl or tl in rl:
            return room["name"]

    # ── 2. Extract type + number ──────────────────────────────────────────────
    room_type   = _extract_type(text)
    room_number = _extract_number(text)

    print(f"[MATCH] type='{room_type}' number='{room_number}'", flush=True)

    if not room_type and not room_number:
        return ""

    # ── 3. Bathroom — no number needed ────────────────────────────────────────
    if room_type == "Bathroom":
        for room in rooms:
            if room["name"] == "Bathroom":
                return room["name"]
        return ""

    # ── 4. Score all rooms ────────────────────────────────────────────────────
    candidates = []
    for room in rooms:
        name = room["name"]
        score = 0

        # Type match
        if room_type:
            if not name.startswith(room_type):
                continue
            score += 50

        # Number match
        if room_number:
            name_nums = re.findall(r'\d+', name)
            if not name_nums or name_nums[0] != room_number:
                continue
            score += 50

        # A/B suffix
        score += _suffix_score(text, name)
        candidates.append((score, name))

    # ── 5. Number only fallback (no type detected) ───────────────────────────
    if not candidates and room_number and not room_type:
        for room in rooms:
            name = room["name"]
            name_nums = re.findall(r'\d+', name)
            if name_nums and name_nums[0] == room_number:
                score = 30 + _suffix_score(text, name)
                candidates.append((score, name))

    if not candidates:
        return ""

    candidates.sort(key=lambda x: x[0], reverse=True)
    best = candidates[0][1]
    print(f"[MATCH] → '{best}'", flush=True)
    return best


def get_room_node_id(room_name: str, map_data: dict) -> str:
    for room in map_data.get("rooms", []):
        if room["name"] == room_name:
            return room["nodeId"]
    return ""


def list_all_rooms(map_data: dict) -> list:
    return [r["name"] for r in map_data.get("rooms", [])]
