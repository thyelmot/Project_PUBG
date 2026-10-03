"""Make review sheets, not a visual PASS certificate. Synthetic evidence only."""
import argparse
import csv
import hashlib
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.image as mpimg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    figures = sorted((args.evidence / "figures").rglob("*.png"))
    if not figures:
        parser.error("No fixture PNGs; do not scan production directories.")
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for index, file in enumerate(figures):
        pixels = mpimg.imread(file)
        rows.append({"index": index + 1, "figure": str(file.relative_to(args.evidence)),
            "width": pixels.shape[1], "height": pixels.shape[0],
            "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
            "review_sheet": f"sheet_{index // 3 + 1:02d}.png",
            "status": "decoded_only; manual source/label review required"})
    with (args.output / "figure_inventory.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    for offset in range(0, len(figures), 3):
        fig, axes = plt.subplots(3, 1, figsize=(18, 20))
        for axis, file in zip(axes, figures[offset:offset + 3]):
            axis.imshow(mpimg.imread(file))
            axis.set_title(str(file.relative_to(args.evidence)), fontsize=12)
        for axis in axes:
            axis.axis("off")
        fig.tight_layout()
        fig.savefig(args.output / f"sheet_{offset // 3 + 1:02d}.png", dpi=130)
        plt.close(fig)
    print(f"Decoded {len(figures)} PNGs; created {(len(figures) + 2) // 3} review sheets; no visual acceptance assigned.")


if __name__ == "__main__":
    main()
