#!/usr/bin/env python3
"""
Image-diff filtering — Étape 2 du runbook extraction-frames-induction.

Usage :
  scripts/diff-frames.py <samples_dir> [--roi x,y,w,h] [--threshold 12.0] [--cadence N] --output transitions.md

- Parcourt les samples par ordre lexicographique (sample-0001.png, sample-0002.png, …).
- Pour chaque paire (n, n+1) : convertit en gris, applique le ROI optionnel (proportions 0..1),
  calcule diff_mean = moyenne |pixel_n - pixel_{n+1}|.
- Si diff_mean > threshold → ligne ajoutée au tableau de sortie.

ROI par défaut : 0,0,1,1 (plein cadre, pas d'exclusion).
Cadence : récupérée depuis <samples_dir>/.cadence si présent, sinon --cadence (défaut 20).

Sortie : tableau markdown # | sample_path | timestamp | diff_mean.
"""

import argparse
import os
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("❌ Pillow requis : pip install Pillow", file=sys.stderr)
    sys.exit(1)


def parse_roi(roi_str: str) -> tuple[float, float, float, float]:
    parts = [p.strip() for p in roi_str.split(",")]
    if len(parts) != 4:
        raise ValueError(f"ROI doit être x,y,w,h en proportions 0..1 (reçu: {roi_str})")
    x, y, w, h = (float(p) for p in parts)
    for v, name in ((x, "x"), (y, "y"), (w, "w"), (h, "h")):
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"ROI {name}={v} hors plage 0..1")
    if x + w > 1.0 + 1e-6 or y + h > 1.0 + 1e-6:
        raise ValueError(f"ROI dépasse le cadre : x+w={x+w}, y+h={y+h}")
    return x, y, w, h


def crop_roi(img: Image.Image, roi: tuple[float, float, float, float]) -> Image.Image:
    x, y, w, h = roi
    if (x, y, w, h) == (0.0, 0.0, 1.0, 1.0):
        return img
    iw, ih = img.size
    left = int(x * iw)
    top = int(y * ih)
    right = int((x + w) * iw)
    bottom = int((y + h) * ih)
    return img.crop((left, top, right, bottom))


def diff_mean(prev: Image.Image, curr: Image.Image) -> float:
    if prev.size != curr.size:
        curr = curr.resize(prev.size)
    p = prev.convert("L")
    c = curr.convert("L")
    pdata = p.tobytes()
    cdata = c.tobytes()
    n = len(pdata)
    if n == 0:
        return 0.0
    total = sum(abs(pdata[i] - cdata[i]) for i in range(n))
    return total / n


def fmt_timestamp(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("samples_dir", help="Répertoire contenant sample-NNNN.png produits par sample-frames.sh")
    ap.add_argument("--roi", default="0,0,1,1", help="x,y,w,h en proportions 0..1 (défaut: plein cadre)")
    ap.add_argument("--threshold", type=float, default=12.0, help="Seuil diff_mean (défaut: 12.0)")
    ap.add_argument("--cadence", type=int, default=None, help="Cadence en secondes (override de .cadence)")
    ap.add_argument("--output", required=True, help="Fichier markdown de sortie")
    args = ap.parse_args()

    samples_dir = Path(args.samples_dir)
    if not samples_dir.is_dir():
        print(f"❌ Répertoire introuvable : {samples_dir}", file=sys.stderr)
        return 1

    samples = sorted(samples_dir.glob("sample-*.png"))
    if len(samples) < 2:
        print(f"❌ Au moins 2 samples requis (trouvé: {len(samples)})", file=sys.stderr)
        return 1

    cadence_file = samples_dir / ".cadence"
    if args.cadence is not None:
        cadence = args.cadence
    elif cadence_file.is_file():
        cadence = int(cadence_file.read_text().strip())
    else:
        cadence = 20
        print(f"⚠ Cadence non trouvée, défaut: {cadence}s", file=sys.stderr)

    try:
        roi = parse_roi(args.roi)
    except ValueError as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    print(f"→ Samples: {len(samples)} dans {samples_dir}", file=sys.stderr)
    print(f"→ ROI: {roi}", file=sys.stderr)
    print(f"→ Threshold: {args.threshold}", file=sys.stderr)
    print(f"→ Cadence: {cadence}s", file=sys.stderr)

    transitions: list[tuple[int, str, str, float]] = []
    prev_img: Image.Image | None = None
    for idx, sample in enumerate(samples):
        with Image.open(sample) as raw:
            img = crop_roi(raw, roi).copy()
        if prev_img is not None:
            d = diff_mean(prev_img, img)
            if d > args.threshold:
                ts_seconds = idx * cadence
                transitions.append((idx, str(sample), fmt_timestamp(ts_seconds), d))
        prev_img = img

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        f.write("# Transitions détectées\n\n")
        f.write(f"- Samples: {len(samples)} (cadence {cadence}s)\n")
        f.write(f"- ROI: {','.join(str(v) for v in roi)}\n")
        f.write(f"- Seuil: {args.threshold}\n")
        f.write(f"- Transitions retenues: {len(transitions)} ({len(transitions)/max(1, len(samples)-1)*100:.1f}%)\n\n")
        f.write("| # | sample | timestamp | diff_mean |\n")
        f.write("|---|---|---|---|\n")
        for i, (idx, path, ts, d) in enumerate(transitions, 1):
            f.write(f"| {i} | `{path}` | `{ts}` | {d:.2f} |\n")

    print(f"✓ {len(transitions)} transitions → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
