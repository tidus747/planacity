"""Portable Windows artifact naming, icon generation, and archive layout."""

import hashlib
import struct
import zipfile
from pathlib import Path

import pytest
from PySide6.QtGui import QImage

from scripts import package_windows


def test_preview_version_maps_to_semver_artifact_name() -> None:
    assert package_windows.release_label("0.4.0.dev0") == "0.4.0-dev.0"
    assert package_windows.artifact_stem("0.4.0.dev1") == "Planacity-v0.4.0-dev.1-windows-x64"
    assert package_windows.release_label("0.4.0") == "0.4.0"
    with pytest.raises(ValueError, match="Unsupported development version"):
        package_windows.release_label("0.4.0.devnext")


def test_windows_icon_contains_every_required_resolution(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    image = QImage(512, 512, QImage.Format.Format_ARGB32)
    image.fill(0xFF1266DD)
    assert image.save(str(source))
    destination = tmp_path / "planacity.ico"

    package_windows.write_windows_icon(source, destination)

    payload = destination.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", payload)
    assert (reserved, kind, count) == (0, 1, len(package_windows.ICON_SIZES))
    widths = [struct.unpack_from("<B", payload, 6 + 16 * index)[0] for index in range(count)]
    assert widths == [16, 24, 32, 48, 64, 128, 0]
    assert QImage(str(destination)).isNull() is False


def test_archive_has_one_versioned_root_and_matching_checksum(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version = "0.4.0.dev7"
    staged = tmp_path / package_windows.artifact_stem(version)
    staged.mkdir()
    (staged / "Planacity.exe").write_bytes(b"preview")
    (staged / "README-WINDOWS.txt").write_text("Preview", encoding="ascii")
    artifact_root = tmp_path / "artifacts"
    monkeypatch.setattr(package_windows, "ARTIFACT_ROOT", artifact_root)

    archive, checksum = package_windows.archive_distribution(staged, version)

    with zipfile.ZipFile(archive) as bundle:
        assert bundle.namelist() == [
            f"{staged.name}/Planacity.exe",
            f"{staged.name}/README-WINDOWS.txt",
        ]
    expected = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert checksum.read_text(encoding="ascii") == f"{expected}  {archive.name}\n"


def test_safe_reset_keeps_target_directory_and_clears_contents(tmp_path: Path) -> None:
    target = tmp_path / "windows"
    nested = target / "old"
    nested.mkdir(parents=True)
    (nested / "artifact.txt").write_text("old", encoding="ascii")
    (target / "old.zip").write_bytes(b"old")

    package_windows._safe_reset(target, tmp_path)

    assert target.is_dir()
    assert list(target.iterdir()) == []
