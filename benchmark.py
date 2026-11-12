"""Mesure du temps de traitement, indépendamment de PySide6.

Depuis le dossier bg_stylizer :
    python benchmark.py "C:\\chemin\\vers\\photo.jpg"
    python benchmark.py "C:\\chemin\\vers\\photo.jpg" --runs 5
"""
import argparse
import statistics
import time
from pathlib import Path

from PIL import Image

from processor import process_image
from style_randomizer import DEFAULT_PARAMETERS


def main():
    parser = argparse.ArgumentParser(description="Mesurer les performances du moteur Image Stylizer")
    parser.add_argument("image", type=Path, help="Chemin d'une image à tester (ne sera pas modifiée)")
    parser.add_argument("--runs", type=int, default=3, help="Nombre de répétitions (défaut : 3)")
    args = parser.parse_args()
    if args.runs < 1 or args.runs > 20:
        parser.error("--runs doit être compris entre 1 et 20")
    if not args.image.is_file():
        parser.error(f"Fichier introuvable : {args.image}")

    with Image.open(args.image) as source:
        original = source.convert("RGB")

    w, h = original.size
    print(f"Image : {args.image.name} | {w} x {h} | {w*h/1e6:.2f} MP")
    print("Mesure du traitement uniquement (hors ouverture et sauvegarde du fichier).")

    scenarios = [
        ("Valeurs par défaut", dict(DEFAULT_PARAMETERS)),
        (
            "Bruit + contraste + vignettage",
            dict(DEFAULT_PARAMETERS,
                 noise_amount=8,
                 noise_seed=2026,
                 contrast_enabled=True,
                 contrast_factor=1.3,
                 vignette_enabled=True,
                 vignette_amount=40),
        ),
    ]

    for name, params in scenarios:
        times = []
        for _ in range(args.runs):
            started = time.perf_counter()
            result = process_image(original, params)
            times.append(time.perf_counter() - started)
            del result
        print(f"{name} : médiane {statistics.median(times):.3f} s "
              f"(min {min(times):.3f}, max {max(times):.3f}, n={len(times)})")


if __name__ == "__main__":
    main()
