import json
import ast
import os
import sys

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def verify_all_notebooks():
    notebook_files = [
        "00_setup.ipynb",
        "01_download_validate.ipynb",
        "02_data_quality_and_structure.ipynb",
        "03_build_player_match.ipynb",
        "04_combat_timing.ipynb",
        "05_eda.ipynb",
        "06_rq1_analysis.ipynb"
    ]

    all_passed = True
    print("=== KIỂM TOÁN CẤU TRÚC VÀ CÚ PHÁP NOTEBOOK 00-06 ===")

    for nb_name in notebook_files:
        path = os.path.join("notebooks", nb_name)
        if not os.path.exists(path):
            print(f"[FAIL] File not found: {path}")
            all_passed = False
            continue

        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        assert "cells" in nb, f"{nb_name} missing cells"
        assert "nbformat" in nb, f"{nb_name} missing nbformat"

        code_cells = [c for c in nb["cells"] if c.get("cell_type") == "code"]
        md_cells = [c for c in nb["cells"] if c.get("cell_type") == "markdown"]

        # Check for empty cells
        empty_cells = []
        for idx, c in enumerate(nb["cells"]):
            content = "".join(c.get("source", [])).strip()
            if not content:
                empty_cells.append(idx)

        # Check syntax of code cells
        syntax_errors = []
        for idx, c in enumerate(code_cells):
            src = "".join(c.get("source", []))
            lines = [l for l in src.split("\n") if not l.strip().startswith("%") and not l.strip().startswith("!")]
            clean_src = "\n".join(lines)
            try:
                ast.parse(clean_src)
            except SyntaxError as e:
                syntax_errors.append((idx, str(e)))

        if empty_cells or syntax_errors:
            all_passed = False
            print(f"[FAIL] {nb_name}: {len(empty_cells)} empty cells, {len(syntax_errors)} syntax errors.")
            for err in syntax_errors:
                print(f"       Code cell {err[0]}: {err[1]}")
        else:
            print(f"[PASS] {nb_name:<36}: {len(nb['cells']):2d} cells ({len(md_cells):2d} markdown, {len(code_cells):2d} code). Cú pháp chuẩn xác 100%.")

    if all_passed:
        print("\n=> TOÀN BỘ 7 NOTEBOOK TỪ 00 ĐẾN 06 ĐẠT CHUẨN CẤU TRÚC VÀ CÚ PHÁP.")
    else:
        print("\n=> PHÁT HIỆN LỖI TRONG CÁC NOTEBOOK!")
        sys.exit(1)

if __name__ == "__main__":
    verify_all_notebooks()
