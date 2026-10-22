"""Build, smoke-test, and archive the portable Windows distribution."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import struct
import subprocess
import sys
import sysconfig
import tempfile
import tomllib
import zipfile
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "build" / "windows"
ARTIFACT_ROOT = ROOT / "dist" / "windows"
DEPLOY_CONFIG = ROOT / "packaging" / "windows" / "pysidedeploy.spec"
ENTRY_POINT = ROOT / "packaging" / "windows" / "Planacity.py"
DEPLOYED_DIR = BUILD_ROOT / "Planacity.dist"
NUITKA_CACHE = ROOT / "build" / "nuitka-cache"
ICON_SOURCE = ROOT / "src" / "planacity" / "resources" / "images" / "planacity-mark.png"
ICON_OUTPUT = BUILD_ROOT / "planacity.ico"
WINDOWS_GUIDE = ROOT / "packaging" / "windows" / "README-WINDOWS.txt"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as stream:
        return str(tomllib.load(stream)["project"]["version"])


def release_label(version: str) -> str:
    """Use one SemVer-friendly label for artifacts and preview tags."""
    marker = ".dev"
    if marker not in version:
        return version
    base, number = version.rsplit(marker, 1)
    if not number.isdigit():
        raise ValueError(f"Unsupported development version: {version}")
    return f"{base}-dev.{number}"


def artifact_stem(version: str) -> str:
    return f"Planacity-v{release_label(version)}-windows-x64"


def _png_bytes(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
        raise ValueError("Could not encode a Windows icon frame.")
    return bytes(data)


def write_windows_icon(source: Path, destination: Path) -> None:
    """Write a multi-resolution ICO containing PNG-compressed frames."""
    original = QImage(str(source))
    if original.isNull():
        raise ValueError(f"Cannot read icon source: {source}")
    frames: list[tuple[int, bytes]] = []
    for size in ICON_SIZES:
        canvas = QImage(size, size, QImage.Format.Format_ARGB32)
        canvas.fill(Qt.GlobalColor.transparent)
        scaled = original.scaled(
            size,
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(canvas)
        painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
        painter.end()
        frames.append((size, _png_bytes(canvas)))

    destination.parent.mkdir(parents=True, exist_ok=True)
    offset = 6 + 16 * len(frames)
    with destination.open("wb") as stream:
        stream.write(struct.pack("<HHH", 0, 1, len(frames)))
        for size, payload in frames:
            encoded_size = 0 if size == 256 else size
            stream.write(
                struct.pack(
                    "<BBBBHHII",
                    encoded_size,
                    encoded_size,
                    0,
                    0,
                    1,
                    32,
                    len(payload),
                    offset,
                )
            )
            offset += len(payload)
        for _, payload in frames:
            stream.write(payload)


def _safe_reset(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    if not resolved.is_relative_to(parent.resolve()) or resolved == parent.resolve():
        raise ValueError(f"Refusing to reset unsafe path: {resolved}")
    resolved.mkdir(parents=True, exist_ok=True)
    for entry in resolved.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _deployment_tool_path() -> Path:
    executable_name = "pyside6-deploy.exe" if sys.platform == "win32" else "pyside6-deploy"
    return Path(sysconfig.get_path("scripts")) / executable_name


def deploy() -> None:
    if sys.platform != "win32":
        raise RuntimeError("The portable Windows package must be built on Windows.")
    if platform.machine().lower() not in {"amd64", "x86_64"}:
        raise RuntimeError("The portable Windows preview requires an x64 build host.")
    _safe_reset(BUILD_ROOT, ROOT / "build")
    write_windows_icon(ICON_SOURCE, ICON_OUTPUT)
    generated_config = BUILD_ROOT / "pysidedeploy.spec"
    shutil.copy2(DEPLOY_CONFIG, generated_config)
    candidate = _deployment_tool_path()
    if not candidate.is_file():
        raise FileNotFoundError("pyside6-deploy is not installed beside the active Python.")
    deploy_command = str(candidate)
    environment = os.environ.copy()
    environment["NUITKA_CACHE_DIR"] = str(NUITKA_CACHE)
    subprocess.run(
        [
            deploy_command,
            str(ENTRY_POINT),
            "-c",
            str(generated_config),
            "--force",
        ],
        cwd=ROOT,
        env=environment,
        check=True,
    )
    executable = DEPLOYED_DIR / "Planacity.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"Deployment did not produce {executable}")


def smoke_test(executable: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PLANACITY_PACKAGE_SMOKE_TEST"] = "1"
    environment["PYTHONNOUSERSITE"] = "1"
    environment["QT_QPA_PLATFORM"] = "offscreen"
    with tempfile.TemporaryDirectory(prefix="planacity-package-smoke-") as working_directory:
        result = subprocess.run(
            [str(executable)],
            cwd=working_directory,
            env=environment,
            timeout=30,
            check=False,
        )
    if result.returncode != 0:
        raise RuntimeError(f"Packaged Planacity smoke test exited with {result.returncode}.")


def stage_distribution(version: str) -> Path:
    destination = BUILD_ROOT / artifact_stem(version)
    _safe_reset(destination, BUILD_ROOT)
    for entry in DEPLOYED_DIR.iterdir():
        target = destination / entry.name
        if entry.is_dir():
            shutil.copytree(entry, target)
        else:
            shutil.copy2(entry, target)
    shutil.copy2(WINDOWS_GUIDE, destination / "README-WINDOWS.txt")
    shutil.copy2(ROOT / "LICENSE", destination / "LICENSE.txt")
    examples = destination / "examples"
    examples.mkdir()
    shutil.copy2(
        ROOT / "examples" / "moon-heist.planacity.json",
        examples / "moon-heist.planacity.json",
    )
    return destination


def archive_distribution(staged: Path, version: str) -> tuple[Path, Path]:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    archive = ARTIFACT_ROOT / f"{artifact_stem(version)}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    archive.unlink(missing_ok=True)
    checksum.unlink(missing_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for source in sorted(staged.rglob("*")):
            if source.is_file():
                bundle.write(source, source.relative_to(staged.parent))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, checksum


def main() -> int:
    version = project_version()
    deploy()
    smoke_test(DEPLOYED_DIR / "Planacity.exe")
    staged = stage_distribution(version)
    archive, checksum = archive_distribution(staged, version)
    print(f"Built {archive.relative_to(ROOT)}")
    print(f"Checksum {checksum.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
