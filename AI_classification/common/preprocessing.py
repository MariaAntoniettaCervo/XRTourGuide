from pathlib import Path
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
import cv2
import io
import random
import base64


INPUT_SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)
MODEL_NAME = "EfficientNetLite0"
MODEL_OUTPUT_DIM = 1280


def preprocess_image(pil_img: Image.Image) -> np.ndarray:
    """Replica ESATTAMENTE il preprocessing di _preprocessImage in Dart."""
    pil_img = pil_img.convert("RGB")
    w, h = pil_img.size
    shortest = min(w, h)

    # 1. Resize con scala 256/shortest (identico a Dart)
    scale = 256 / shortest
    new_w, new_h = round(w * scale), round(h * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.BICUBIC)
    print(f"  [Py] Resized shape: ({new_w}, {new_h})")

    # 2. Center Crop (identico a Dart)
    crop_x = round((new_w - INPUT_SIZE) / 2)
    crop_y = round((new_h - INPUT_SIZE) / 2)
    pil_img = pil_img.crop((crop_x, crop_y, crop_x + INPUT_SIZE, crop_y + INPUT_SIZE))

    img_array = np.array(pil_img, dtype=np.float32)

    # Debug: primi 10 pixel RGB
    pixels_flat = img_array.reshape(-1, 3)
    print(f"  [Py] First 10 cropped RGB pixels:\n{pixels_flat[:10].astype(int)}")

    return img_array

def preprocess_image_dart_compatible(pil_img: Image.Image) -> np.ndarray:
    pil_img = pil_img.convert("RGB")
    w, h = pil_img.size
    shortest = min(w, h)
    scale = 256 / shortest
    new_w, new_h = round(w * scale), round(h * scale)
    pil_img = pil_img.resize((new_w, new_h), Image.BICUBIC)
    crop_x = round((new_w - INPUT_SIZE) / 2)
    crop_y = round((new_h - INPUT_SIZE) / 2)
    pil_img = pil_img.crop((crop_x, crop_y, crop_x + INPUT_SIZE, crop_y + INPUT_SIZE))
    return np.array(pil_img, dtype=np.float32)

def build_orb_input_from_bgr(
    bgr,
    use_clahe=True,
    use_edges=False,
    canny_low=80,
    canny_high=160,
    edge_alpha=0.25
):
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    
    if use_clahe:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)
    
    if use_edges:
        edges = cv2.Canny(gray, canny_low, canny_high)
        blended = cv2.addWeighted(gray, 1.0, edges, edge_alpha, 0.0)
        return blended
    
    return gray

def compute_orb_features_dart_compatible(image_path: Path):
    img = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if img is None:
        return [], np.array([]), 0, 0
    orb_input = build_orb_input_from_bgr(
        img,
        use_clahe=True,
        use_edges=True,
        canny_low=80,
        canny_high=160,
        edge_alpha=0.25
    )
    orb = cv2.ORB_create(nfeatures=5000)
    kp, desc = orb.detectAndCompute(orb_input, None)
    if desc is None or len(kp) == 0:
        return [], np.array([]), 0, 0
    kp_coords = [[float(k.pt[0]), float(k.pt[1])] for k in kp]
    desc = desc.astype(np.uint8)
    rows, cols = desc.shape
    return kp_coords, desc, rows, cols


def build_query_views_pil(pil_img):
    w, h = pil_img.size

    views = {
        # geometriche
        "center": pil_img,
        "crop_center": pil_img.crop(
            (int(w * 0.10), int(h * 0.10), int(w * 0.90), int(h * 0.90))
        ).resize((w, h)),
        "crop_left": pil_img.crop(
            (0, int(h * 0.08), int(w * 0.85), int(h * 0.92))
        ).resize((w, h)),
        "crop_right": pil_img.crop(
            (int(w * 0.15), int(h * 0.08), w, int(h * 0.92))
        ).resize((w, h)),
        "crop_top": pil_img.crop(
            (int(w * 0.08), 0, int(w * 0.92), int(h * 0.85))
        ).resize((w, h)),
        "crop_bottom": pil_img.crop(
            (int(w * 0.08), int(h * 0.15), int(w * 0.92), h)
        ).resize((w, h)),
        
        "brightness_down_q": ImageEnhance.Brightness(pil_img).enhance(0.82),
        "brightness_up_q": ImageEnhance.Brightness(pil_img).enhance(1.12),
        "contrast_down_q": ImageEnhance.Contrast(pil_img).enhance(0.88),
        "contrast_up_q": ImageEnhance.Contrast(pil_img).enhance(1.12),
    }

    return views

def jpeg_reencode(pil_img, quality=35):
    buf = io.BytesIO()
    pil_img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")

def add_shadow_band(pil_img, darkness=0.35):
    img = np.array(pil_img).astype(np.float32)
    h, w = img.shape[:2]
    x0 = random.randint(0, max(0, w // 2))
    band_w = random.randint(max(10, w // 6), max(20, w // 3))
    x1 = min(w, x0 + band_w)
    img[:, x0:x1, :] *= darkness
    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img)

def make_night_like(pil_img):
    img = np.array(pil_img).astype(np.float32)

    img *= 0.42

    img[..., 2] *= 1.08  # blue
    img[..., 1] *= 0.92  # green
    img[..., 0] *= 0.86  # red

    img = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(img)

def get_query_view_weights():
    return {
        "center": 1.00,
        "crop_center": 0.98,
        "crop_left": 0.92,
        "crop_right": 0.92,
        "crop_top": 0.88,
        "crop_bottom": 0.88,
        "brightness_down_q": 0.90,
        "brightness_up_q": 0.90,
        "contrast_down_q": 0.88,
        "contrast_up_q": 0.88,
    }

def generate_reference_variants(pil_img):
    return {
        "original": pil_img,
        "brightness_down": ImageEnhance.Brightness(pil_img).enhance(0.75),
        "brightness_up": ImageEnhance.Brightness(pil_img).enhance(1.20),
        "contrast_down": ImageEnhance.Contrast(pil_img).enhance(0.80),
        "contrast_up": ImageEnhance.Contrast(pil_img).enhance(1.20),
        "jpeg_low_quality": jpeg_reencode(pil_img, quality=40),
        "night_like": make_night_like(pil_img),
    }
        
def get_reference_variant_weights():
    return {
        "original": 1.00,
        "brightness_down": 0.95,
        "brightness_up": 0.95,
        "contrast_down": 0.93,
        "contrast_up": 0.93,
        "jpeg_low_quality": 0.88,
        "night_like": 0.82,
    }
    
def decode_descriptors_from_base64(desc_b64, rows, cols):
    if not desc_b64 or rows <= 0 or cols <= 0:
        return None
    
    raw = base64.b64decode(desc_b64.encode("utf-8"))
    arr = np.frombuffer(raw, dtype=np.uint8)
    return arr.reshape(rows, cols)

def cosine_similarity_np(a, b):
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom < 1e-8:
        return 0.0
    
    return float(np.dot(a, b) / denom)
