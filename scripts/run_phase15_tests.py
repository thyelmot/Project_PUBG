"""Local synthetic regression only. Never execute the historical All-in-One."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EXCLUDED = {
    "test_all_cells_on_synthetic_data_in_fresh_workspace",
    "test_notebooks_block_out_of_order_cells_and_invalidate_success_on_rerun_failure",
}


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    discovered = list(cases(suite))
    selected = [case for case in discovered if case.id().split(".")[-1] not in EXCLUDED]
    excluded = [case.id() for case in discovered if case not in selected]
    print("Excluded All-in-One execution:", excluded, flush=True)
    print("Selected tests:", len(selected), flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(selected))
    sys.exit(not result.wasSuccessful())
