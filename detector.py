#!/usr/bin/env python3
"""
detector.py — NET-SCAN Core Detection Pipeline
YOLOv8 object detection + cyberpunk OpenCV rendering
100% open source — no API key required
"""

import cv2
import numpy as np
import random
from datetime import datetime
from ultralytics import YOLO

# ── Load model once (module-level) ────────────────────────────────────────────
_model = None

def get_model(weights: str = "yolov8n.pt") -> YOLO:
    global _model
    if _model is None:
        _model = YOLO(weights)
    return _model

# ── BGR color palette ─────────────────────────────────────────────────────────
BGR_YELLOW = (0,   230, 255)
BGR_PINK   = (120,  45, 255)
BGR_CYAN   = (255, 245,   0)
BGR_ORANGE = (0,  107, 255)
BGR_RED    = (0,    0, 255)
BGR_DIM    = (60,  60,  80)

SEVERITY_BGR = {
    "low":      BGR_YELLOW,
    "medium":   BGR_ORANGE,
    "high":     BGR_PINK,
    "critical": BGR_RED,
}

# ── Classes considered anomalies by default ───────────────────────────────────
ANOMALY_CLASSES = {
    "knife", "scissors", "gun", "pistol", "rifle",
    "cell phone", "fire", "smoke",
}

# Classes that are unusual in most indoor/outdoor scenes
CONTEXT_ANOMALY = {
    "bear", "elephant", "zebra", "giraffe", "horse",
    "cow", "sheep", "skis", "snowboard", "surfboard",
}

SEVERITY_MAP = {
    "knife": "critical", "gun": "critical", "pistol": "critical",
    "rifle": "critical", "fire": "critical",
    "scissors": "high",  "smoke": "high",
    "cell phone": "medium",
}

def classify_anomaly(label: str) -> tuple[bool, str, str]:
    """Returns (is_anomaly, severity, reason)"""
    l = label.lower()
    if l in ANOMALY_CLASSES:
        sev = SEVERITY_MAP.get(l, "high")
        return True, sev, f"Threat object detected: {label}"
    if l in CONTEXT_ANOMALY:
        return True, "medium", f"Unexpected entity in scene: {label}"
    return False, "low", ""

# ── Detection ─────────────────────────────────────────────────────────────────
def run_detection(image_path: str, weights: str = "yolov8n.pt",
                  conf_thresh: float = 0.35) -> dict:
    """Run YOLOv8 on an image. Returns structured result dict."""
    model = get_model(weights)
    results = model(image_path, conf=conf_thresh, verbose=False)
    r = results[0]

    img = cv2.imread(image_path)
    h, w = img.shape[:2]

    objects = []
    for i, box in enumerate(r.boxes):
        x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
        conf  = round(float(box.conf[0]) * 100)
        label = r.names[int(box.cls[0])]

        is_anom, severity, reason = classify_anomaly(label)

        objects.append({
            "id":           f"obj_{i+1}",
            "name":         label,
            "category":     label,
            "is_anomaly":   is_anom,
            "anomaly_reason": reason if is_anom else None,
            "confidence":   conf,
            "severity":     severity,
            "threat_tag":   label.upper() if is_anom else None,
            "bbox_pct": {
                "x": round(x1 / w * 100, 1),
                "y": round(y1 / h * 100, 1),
                "w": round((x2 - x1) / w * 100, 1),
                "h": round((y2 - y1) / h * 100, 1),
            },
            "description": f"{label} detected with {conf}% confidence.",
        })

    anomalies = [o for o in objects if o["is_anomaly"]]
    threat = min(100, len(anomalies) * 25 + (10 if objects else 0))

    return {
        "objects":          objects,
        "scene_summary":    f"{len(objects)} object(s) detected. {len(anomalies)} anomaly/anomalies flagged.",
        "overall_threat":   threat,
        "corp_assessment":  (
            f"{len(anomalies)} threat(s) require immediate response, citizen."
            if anomalies else "Sector nominal. No threats detected, citizen."
        ),
    }

# ── Cyberpunk rendering ───────────────────────────────────────────────────────
def apply_cyberpunk_base(img: np.ndarray) -> np.ndarray:
    lut = np.arange(256, dtype=np.float32)
    b_lut = np.clip(lut * 1.05, 0, 255).astype(np.uint8)
    r_lut = np.clip(lut * 0.88, 0, 255).astype(np.uint8)
    g_lut = np.clip(lut * 0.86, 0, 255).astype(np.uint8)
    b, g, r = cv2.split(img)
    img = cv2.merge([cv2.LUT(b, b_lut), cv2.LUT(g, g_lut), cv2.LUT(r, r_lut)])
    for y in range(0, img.shape[0], 4):
        img[y, :] = (img[y, :] * 0.70).astype(np.uint8)
    rows, cols = img.shape[:2]
    X, Y = np.meshgrid(np.linspace(-1, 1, cols), np.linspace(-1, 1, rows))
    mask = np.clip(1 - (X**2 + Y**2) * 0.55, 0.28, 1.0)
    return (img * mask[:, :, np.newaxis]).astype(np.uint8)


def add_rain_streaks(img: np.ndarray, count: int = 60) -> np.ndarray:
    h, w = img.shape[:2]
    ov = img.copy()
    for _ in range(count):
        x  = random.randint(0, w - 1)
        y1 = random.randint(0, h - 2)
        y2 = min(y1 + random.randint(10, 55), h - 1)
        col = random.choice([BGR_CYAN, BGR_YELLOW, BGR_PINK])
        cv2.line(ov, (x, y1), (x, y2), col, 1)
    return cv2.addWeighted(img, 0.91, ov, 0.09, 0)


def draw_cp_bbox(img, x1, y1, x2, y2, color, is_anomaly, label, sub=""):
    h, w = img.shape[:2]
    glow = img.copy()
    cv2.rectangle(glow, (x1, y1), (x2, y2), color, 7)
    img = cv2.addWeighted(img, 0.72, glow, 0.28, 0)
    cv2.rectangle(img, (x1, y1), (x2, y2), color, 3 if is_anomaly else 2)

    bl = max(16, min(30, (x2 - x1) // 4, (y2 - y1) // 4))
    for cx, cy, dx, dy in [(x1,y1,1,1),(x2,y1,-1,1),(x1,y2,1,-1),(x2,y2,-1,-1)]:
        cv2.line(img, (cx, cy), (cx + dx * bl, cy), color, 4)
        cv2.line(img, (cx, cy), (cx, cy + dy * bl), color, 4)
        cv2.line(img, (cx+dx*5, cy+dy*5), (cx+dx*(bl//2), cy+dy*5), color, 1)

    cut = 10
    cv2.line(img, (x1, y1 + cut), (x1 + cut, y1), color, 3)

    font = cv2.FONT_HERSHEY_SIMPLEX
    (lw, lh), baseline = cv2.getTextSize(label, font, 0.46, 2)
    lx, ly = x1, max(y1 - 2, lh + 6)
    pts = np.array([
        [lx,       ly - lh - baseline - 4],
        [lx+lw+14, ly - lh - baseline - 4],
        [lx+lw+8,  ly + baseline],
        [lx,       ly + baseline],
    ], np.int32)
    cv2.fillPoly(img, [pts], color)
    tc = (0, 0, 0) if color == BGR_YELLOW else (255, 255, 255)
    cv2.putText(img, label, (lx + 3, ly - 1), font, 0.46, tc, 2, cv2.LINE_AA)

    if sub:
        cv2.putText(img, sub[:55], (x1, min(y2 + 15, h - 4)),
                    font, 0.33, color, 1, cv2.LINE_AA)
    return img


def draw_hud(img, result: dict) -> np.ndarray:
    h, w = img.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    objects   = result.get("objects", [])
    anomalies = [o for o in objects if o.get("is_anomaly")]
    threat    = result.get("overall_threat", 0)
    ts        = datetime.now().strftime("%Y.%m.%d // %H:%M:%S")
    tc        = BGR_RED if threat >= 70 else BGR_ORANGE if threat >= 40 else BGR_YELLOW

    lines = [
        ("ARASAKA CORP // NET-SCAN v6.6.6",              BGR_YELLOW, 0.50, 2),
        (f"TIMESTAMP: {ts}",                              BGR_DIM,    0.35, 1),
        (f"TARGETS IDENTIFIED : {len(objects)}",          BGR_YELLOW, 0.38, 1),
        (f"THREATS FLAGGED    : {len(anomalies)}",
         BGR_RED if anomalies else BGR_YELLOW,             0.38,       1),
        (f"THREAT INDEX       : {threat}%",               tc,         0.38, 2),
    ]
    y_off = 22
    for txt, col, sc, th in lines:
        (tw, txh), _ = cv2.getTextSize(txt, font, sc, th)
        cv2.rectangle(img, (0, y_off - txh - 3), (tw + 14, y_off + 5), (8, 5, 14), -1)
        cv2.putText(img, txt, (6, y_off), font, sc, col, th, cv2.LINE_AA)
        y_off += int(sc * 42 + 4)

    # Threat bar top-right
    bw, bh = 180, 14
    bx, by = w - bw - 14, 14
    cv2.rectangle(img, (bx-2, by-2), (bx+bw+2, by+bh+2), BGR_YELLOW, 1)
    fill = int(threat / 100 * bw)
    cv2.rectangle(img, (bx, by), (bx + fill, by + bh), tc, -1)
    cv2.putText(img, f"THREAT {threat}%", (bx, by - 6), font, 0.38, BGR_YELLOW, 1, cv2.LINE_AA)
    for i in range(10):
        tx = bx + int(i * bw / 10)
        cv2.line(img, (tx, by), (tx, by + bh), (8, 5, 14), 2)

    # Corner brackets
    bl = 55
    for cx, cy, dx, dy in [(0,0,1,1),(w-1,0,-1,1),(0,h-1,1,-1),(w-1,h-1,-1,-1)]:
        cv2.line(img, (cx, cy), (cx + dx*bl, cy), BGR_YELLOW, 3)
        cv2.line(img, (cx, cy), (cx, cy + dy*bl), BGR_YELLOW, 3)
        cv2.line(img, (cx+dx*9, cy+dy*9), (cx+dx*(bl-9), cy+dy*9), BGR_YELLOW, 1)
        cv2.line(img, (cx+dx*9, cy+dy*9), (cx+dx*9, cy+dy*(bl-9)), BGR_YELLOW, 1)

    cv2.line(img, (bl+10, 0),   (0, bl+10),   BGR_YELLOW, 1)
    cv2.line(img, (w-bl-10, 0), (w, bl+10),   BGR_YELLOW, 1)

    # Bottom note
    note = f"NET-SCAN: {result.get('corp_assessment', '')}"[:90]
    (nw, nh), _ = cv2.getTextSize(note, font, 0.37, 1)
    cv2.rectangle(img, (0, h - nh - 16), (nw + 12, h), (8, 4, 16), -1)
    cv2.line(img, (0, h - nh - 18), (nw + 12, h - nh - 18), BGR_YELLOW, 1)
    cv2.putText(img, note, (6, h - 5), font, 0.37, BGR_YELLOW, 1, cv2.LINE_AA)

    # Random glitch stripe
    if random.random() > 0.6:
        gy = random.randint(0, h - 6)
        gw = random.randint(40, 200)
        gx = random.randint(0, w - gw)
        strip = img[gy:gy+3, gx:gx+gw].copy()
        strip = np.roll(strip, random.randint(-8, 8), axis=1)
        img[gy:gy+3, gx:gx+gw] = strip

    return img


def render_output(image_path: str, result: dict, output_path: str) -> str:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    h, w = img.shape[:2]

    img = apply_cyberpunk_base(img)
    img = add_rain_streaks(img, count=60)

    for obj in result.get("objects", []):
        b = obj.get("bbox_pct", {})
        if not b:
            continue
        x1 = int(b["x"] / 100 * w);  y1 = int(b["y"] / 100 * h)
        x2 = x1 + int(b["w"] / 100 * w); y2 = y1 + int(b["h"] / 100 * h)
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w-1, x2), min(h-1, y2)

        is_anom = obj.get("is_anomaly", False)
        color   = SEVERITY_BGR.get(obj["severity"], BGR_PINK) if is_anom else BGR_YELLOW
        tag     = obj.get("threat_tag") or obj["name"].upper()
        label   = f"{'[THREAT] ' if is_anom else '[ID] '}{tag}  {obj['confidence']}%"
        sub     = obj.get("anomaly_reason", "") if is_anom else ""

        img = draw_cp_bbox(img, x1, y1, x2, y2, color, is_anom, label, sub)

    img = draw_hud(img, result)
    cv2.imwrite(output_path, img)
    return output_path
