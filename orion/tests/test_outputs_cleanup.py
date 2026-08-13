import time

from core.outputs_cleanup import purge_old_outputs


def test_retention_days_zero_or_less_is_a_noop(tmp_path):
    old_file = tmp_path / "old.png"
    old_file.write_text("x")

    deleted = purge_old_outputs(tmp_path, retention_days=0)

    assert deleted == []
    assert old_file.exists()


def test_missing_directory_is_a_noop(tmp_path):
    missing = tmp_path / "does-not-exist"

    assert purge_old_outputs(missing, retention_days=30) == []


def test_deletes_files_older_than_retention_and_keeps_recent_ones(tmp_path):
    now = time.time()
    old_file = tmp_path / "old.png"
    old_file.write_text("x")
    import os

    os.utime(old_file, (now - 40 * 86400, now - 40 * 86400))  # 40 days old

    recent_file = tmp_path / "recent.png"
    recent_file.write_text("x")
    os.utime(recent_file, (now - 5 * 86400, now - 5 * 86400))  # 5 days old

    deleted = purge_old_outputs(tmp_path, retention_days=30, now=now)

    assert deleted == [old_file]
    assert not old_file.exists()
    assert recent_file.exists()


def test_never_touches_files_under_websites_subdir(tmp_path):
    now = time.time()
    site_dir = tmp_path / "websites" / "my-site"
    site_dir.mkdir(parents=True)
    old_site_file = site_dir / "index.html"
    old_site_file.write_text("<html></html>")
    import os

    os.utime(old_site_file, (now - 400 * 86400, now - 400 * 86400))  # very old

    deleted = purge_old_outputs(tmp_path, retention_days=30, now=now)

    assert deleted == []
    assert old_site_file.exists()


def test_returns_deleted_paths_across_nested_subdirectories(tmp_path):
    now = time.time()
    import os

    images_dir = tmp_path / "images"
    images_dir.mkdir()
    old_image = images_dir / "old.png"
    old_image.write_text("x")
    os.utime(old_image, (now - 100 * 86400, now - 100 * 86400))

    deleted = purge_old_outputs(tmp_path, retention_days=30, now=now)

    assert deleted == [old_image]
