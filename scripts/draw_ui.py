"""Draw English replacements for UI textures.

  python -E -P scripts/draw_ui.py [SUBSTRING ...]     only jobs whose path contains one of the substrings

Jobs live in scripts/uidraw/: labels.py (plates, glow captions, headers, ranks) and hints.py (button-hint strips,
help lines, controller diagrams, text-heavy screens); shared helpers in common.py. Each job takes the original PNG
exported by scripts/export_ui.py (game/ui_png/<path>.png), draws the English in a style that imitates the original,
and writes game/images_en/<path>.png (same size). scripts/build_images.py then injects those PNGs. The output is
derived from game art, so it stays in game/ (git-ignored); only the code is committed.
Font: Bahnschrift (Windows) condensed variants are close to the condensed sans used by the stylised UI labels.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from uidraw import common, hints, labels  # noqa: E402

DST = os.path.join(common.ROOT, "game", "images_en")


def main():
    want = sys.argv[1:]
    paths = {}
    for mod in (labels, hints):
        for path, text, style, opt in mod.JOBS:
            if path in paths:
                sys.exit(f"{path}: in both {paths[path]} and {mod.__name__}")
            paths[path] = mod.__name__
            if want and not any(w in path for w in want):
                continue
            base = common.original(path)
            img = mod.draw(base, text, style, opt)
            if img.size != base.size:
                sys.exit(f"{path}: size changed")
            dst = os.path.join(DST, *path.split("/")) + ".png"
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            img.save(dst)
            print(f"{path}: {text!r} -> {os.path.relpath(dst, common.ROOT)}")


if __name__ == "__main__":
    main()
