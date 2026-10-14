"""Run in NB04 after Bootstrap to restore its matching bundled source."""
import ast
import base64
import hashlib
import importlib
import io
import tempfile
import zipfile
from pathlib import Path

from src.data.io import publish_file
from src.data.cleaning import _materialize_groups

expected = "d8487e7755c0118eb4cce7ccf546bd73f1b22100453c02469621fcfe4a49507b"
bootstrap = next(text for text in reversed(In[:-1])
                 if text.startswith("# Bootstrap: runtime mode needs no Drive"))
payload = next(node.value for node in ast.walk(ast.parse(bootstrap))
               if isinstance(node, ast.Constant) and isinstance(node.value, str)
               and node.value.startswith("UEsDB"))
with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload))) as bundle:
    source = bundle.read("src/features/combat_timing.py")
assert hashlib.sha256(source).hexdigest() == expected, "Unexpected notebook bundle"
compile(source, "combat_timing.py", "exec")
target = PROJECT_ROOT / "src/features/combat_timing.py"
old = target.read_bytes()
old_hash = hashlib.sha256(old).hexdigest()
backup_dir = PROJECT_ROOT / "reports/appendix/nb04_drive_import_fix_2026-10-07"
backup = backup_dir / ("combat_timing_before_" + old_hash + ".py")
if old_hash != expected:
    with tempfile.TemporaryDirectory(prefix="nb04_source_") as directory:
        local = Path(directory) / "combat_timing.py"
        local.write_bytes(old)
        publish_file(local, backup)
        assert backup.read_bytes() == old, "Backup mismatch"
        local.write_bytes(source)
        publish_file(local, target)
assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
importlib.invalidate_caches()
from src.features import combat_timing
importlib.reload(combat_timing)
assert callable(combat_timing.audit_match_duration)
assert not combat_timing.evaluate_combat_timing_research_gate(cfg["features"])["ready"]
print("NB04 source restored and import verified:", target)
print("SHA256:", expected)
print("Backup:", backup if old_hash != expected else "source already matches")
print("Research gate preserved. Run initialization next.")
