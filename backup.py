"""
RepairDesk — repair-shop job-card tracker.
backup.py: zip the whole data folder (database + receipts) for safekeeping,
and restore it from a zip.

The zip is timestamped: repairdesk-backup-YYYYMMDD-HHMMSS.zip
"""

import os
import shutil
import tempfile
from datetime import datetime
from zipfile import ZipFile


def data_dir() -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repairdesk_data")
    os.makedirs(d, exist_ok=True)
    return d


def make_backup(dest_folder: str | None = None) -> str:
    """Create a timestamped zip of repairdesk_data. Returns the zip path."""
    folder = dest_folder or os.path.join(data_dir(), "backups")
    os.makedirs(folder, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    zip_path = os.path.join(folder, f"repairdesk-backup-{stamp}.zip")
    with ZipFile(zip_path, "w") as z:
        for root, _dirs, files in os.walk(data_dir()):
            # Don't nest old backups inside a new backup.
            if os.path.basename(root) == "backups":
                continue
            for f in files:
                full = os.path.join(root, f)
                z.write(full, os.path.relpath(full, data_dir()))
    return zip_path


def restore_backup(zip_path: str) -> None:
    """Replace the data folder contents with the zip's. A safety copy of the
    current data folder is kept next to it first."""
    d = data_dir()
    safety = d + "-safety-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    with tempfile.TemporaryDirectory() as tmp:
        # Extract to a temp dir first so a bad zip can't half-destroy live data.
        with ZipFile(zip_path) as z:
            z.extractall(tmp)
        shutil.copytree(d, safety, ignore=shutil.ignore_patterns("backups"))
        try:
            for entry in os.listdir(tmp):
                src = os.path.join(tmp, entry)
                dst = os.path.join(d, entry)
                if os.path.isdir(src):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        except Exception:
            # Roll back to the safety copy on any failure.
            shutil.rmtree(d)
            shutil.move(safety, d)
            raise
    # Restore went fine — the safety copy stays on disk as insurance.
