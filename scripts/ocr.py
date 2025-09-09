import os, sys, json, math, cv2, numpy as np
from pathlib import Path
import torch
from PIL import Image
from transformers import VisionEncoderDecoderModel, TrOCRProcessor

MODEL_NAME = os.getenv("TROCR_MODEL", "microsoft/trocr-base-handwritten")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def load_model():
    processor = TrOCRProcessor.from_pretrained(MODEL_NAME)
    model = VisionEncoderDecoderModel.from_pretrained(MODEL_NAME).to(DEVICE)
    model.eval()
    return processor, model

def read_gray(path):
    img = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Failed to read {path}")
    return img

def deskew(img):
    # Use binary projection to find skew angle
    thr = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thr > 0))
    angle = 0.0
    if len(coords) > 0:
        rect = cv2.minAreaRect(coords)
        angle = rect[-1]
        if angle < -45: angle = -(90 + angle)
        else: angle = -angle
    (h, w) = img.shape
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def enhance(img):
    # Contrast + denoise tuned for pencil/pen on ruled paper
    norm = cv2.normalize(img, None, 0, 255, cv2.NORM_MINMAX)
    blur = cv2.medianBlur(norm, 3)
    # Light unsharp mask
    sharp = cv2.addWeighted(norm, 1.5, cv2.GaussianBlur(norm, (0,0), 1.0), -0.5, 0)
    return cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

def segment_lines(bin_img, min_height=14):
    # Collapse text into horizontal bands using morphological closing then projection
    # Works well on ruled/lined paper
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 3))
    closed = cv2.morphologyEx(bin_img, cv2.MORPH_CLOSE, kernel, iterations=1)
    proj = np.sum((255 - closed) // 255, axis=1)
    # Find contiguous runs where projection > 0
    lines, start = [], None
    for i, v in enumerate(proj):
        if v > 0 and start is None:
            start = i
        elif v == 0 and start is not None:
            if i - start >= min_height:
                lines.append((start, i))
            start = None
    if start is not None and (len(proj) - start) >= min_height:
        lines.append((start, len(proj)))
    return lines

@torch.inference_mode()
def recog_line(processor, model, crop):
    # Expect PIL RGB
    pixel_values = processor(images=crop, return_tensors="pt").pixel_values.to(DEVICE)
    output_ids = model.generate(pixel_values, max_length=128)
    return processor.batch_decode(output_ids, skip_special_tokens=True)[0].strip()

def run_on_image(img_path: Path):
    g = read_gray(img_path)
    g = deskew(g)
    b = enhance(g)
    lines = segment_lines(255 - b)  # work with white text on black for projection logic above
    out = []
    if not lines:
        # fallback: whole page
        txt = recog_line(*MODEL, Image.fromarray(g).convert("RGB"))
        return {"text": txt, "lines": [{"y0":0,"y1":g.shape[0],"text":txt}]}

    for (y0, y1) in lines:
        pad = 4
        y0 = max(0, y0 - pad); y1 = min(g.shape[0], y1 + pad)
        crop = g[y0:y1, :]
        # Remove wide margins; keep central band with content
        colproj = np.sum((255 - b[y0:y1, :]) // 255, axis=0)
        xs = np.where(colproj > 0)[0]
        if len(xs) > 10:
            x0, x1 = max(0, xs[0]-5), min(crop.shape[1], xs[-1]+5)
            crop = crop[:, x0:x1]
        pil = Image.fromarray(crop).convert("RGB")
        text = recog_line(*MODEL, pil)
        out.append({"y0": int(y0), "y1": int(y1), "text": text})
    # Sort by y just in case and stitch with newlines
    out.sort(key=lambda r: r["y0"])
    full_text = "\n".join([r["text"] for r in out]).strip()
    return {"text": full_text, "lines": out}

def main():
    import argparse
    ap = argparse.ArgumentParser(description="Handwritten OCR with TrOCR (handwritten)")
    ap.add_argument("inputs", nargs="+", help="Image files or folders")
    ap.add_argument("--model", default=MODEL_NAME, help="TrOCR model name")
    ap.add_argument("--json", action="store_true", help="Emit JSON alongside .txt")
    args = ap.parse_args()

    global MODEL
    MODEL = load_model()

    paths = []
    for p in args.inputs:
        P = Path(p)
        if P.is_dir():
            paths += [q for q in P.rglob("*") if q.suffix.lower() in {".png",".jpg",".jpeg",".tif",".tiff",".bmp",".webp"}]
        else:
            paths.append(P)

    for path in paths:
        res = run_on_image(path)
        txt_out = path.with_suffix(".txt")
        txt_out.write_text(res["text"], encoding="utf-8")
        if args.json:
            path.with_suffix(".json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] {path} -> {txt_out}")

if __name__ == "__main__":
    main()
