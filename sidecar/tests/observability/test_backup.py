"""Tests for Backup Manager."""

import os
import tempfile
from sentinel.observability.recovery.backup_manager import BackupManager


class TestBackupManager:
    def test_create_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("test data")
            bdir = os.path.join(tmp, "backups")
            bm = BackupManager(backup_dir=bdir, max_backups=5)
            record = bm.create_backup(src, label="test")
            assert record is not None
            assert os.path.isfile(record.path)
            assert record.size_bytes > 0

    def test_backup_nonexistent_source(self):
        bm = BackupManager()
        record = bm.create_backup("/nonexistent/path.db")
        assert record is None

    def test_list_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("data")
            bm = BackupManager(backup_dir=os.path.join(tmp, "bk"))
            bm.create_backup(src, label="first")
            bm.create_backup(src, label="second")
            assert bm.count == 2
            records = bm.list_backups()
            assert len(records) == 2

    def test_max_backups_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("data")
            bm = BackupManager(backup_dir=os.path.join(tmp, "bk"), max_backups=3)
            for i in range(5):
                bm.create_backup(src, label=f"b{i}")
            assert bm.count <= 3

    def test_latest_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("data")
            bm = BackupManager(backup_dir=os.path.join(tmp, "bk"))
            bm.create_backup(src, label="latest_test")
            latest = bm.latest_backup()
            assert latest is not None
            assert "latest_test" in latest.label

    def test_restore_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("original data")
            bm = BackupManager(backup_dir=os.path.join(tmp, "bk"))
            record = bm.create_backup(src)
            assert record is not None
            with open(src, "w") as f:
                f.write("modified data")
            success = bm.restore(record.path, src)
            assert success
            with open(src) as f:
                content = f.read()
            assert content == "original data"

    def test_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "test.db")
            with open(src, "w") as f:
                f.write("data")
            bm = BackupManager(backup_dir=os.path.join(tmp, "bk"))
            bm.create_backup(src)
            s = bm.summary()
            assert s["total_backups"] == 1
            assert s["backup_dir"] == bm.backup_dir
