"""Verify one actual Inno installer in an isolated, reversible local fixture.

Usage: python scripts/verify_installer.py --setup SETUP.exe --bundle BUNDLE
                                        --out RECEIPT.json

Refuses an existing Mira uninstall key. Never removes an existing installation,
recursively cleans a directory, imports user sessions, or starts a network job.
The fixture, logs and offline design screenshots remain as QA evidence; the
newly installed application is uninstalled before a successful receipt.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import time
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = PROJECT_ROOT.parents[1].resolve()
UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


class VerificationError(RuntimeError):
    pass


def filesystem_path(value: str | Path) -> Path:
    """Use Win32 extended paths for I/O, independent of host longPathAware flags.

    Keep these paths out of receipts/confinement comparisons; logical_path
    returns the corresponding ordinary absolute path for those operations.
    """
    if os.name != "nt":
        return Path(value).absolute()
    absolute = os.path.abspath(os.fspath(value))
    if absolute.startswith("\\\\?\\"):
        return Path(absolute)
    if absolute.startswith("\\\\.\\"):
        raise VerificationError("Win32 device paths are not supported.")
    if absolute.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + absolute[2:])
    return Path("\\\\?\\" + absolute)


def logical_path(value: str | Path) -> Path:
    resolved = str(filesystem_path(Path(value).expanduser()).resolve())
    if resolved.startswith("\\\\?\\UNC\\"):
        resolved = "\\\\" + resolved[8:]
    elif resolved.startswith("\\\\?\\"):
        resolved = resolved[4:]
    return Path(resolved)


def file_names(root: Path):
    """Enumerate using extended paths and return ordinary relative file names."""
    native_root = filesystem_path(root)
    if not native_root.exists():
        return
    for path in native_root.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise VerificationError("Linked fixture/bundle entries are not supported by this smoke test.")
        if path.is_file():
            yield path.relative_to(native_root).as_posix()


def task_path(value: str | Path, label: str) -> Path:
    """Resolve before every mutation and confine it to this task's workspace."""
    result = logical_path(value)
    if result == TASK_ROOT or not result.is_relative_to(TASK_ROOT):
        raise VerificationError(f"{label} must be inside the task workspace.")
    return result


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with filesystem_path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def installer_app_id() -> str:
    source = filesystem_path(PROJECT_ROOT / "scripts" / "installer.iss").read_text(encoding="utf-8-sig")
    match = re.search(r"(?mi)^AppId=\{\{([0-9a-f-]{36})\}\s*$", source)
    if not match:
        raise VerificationError("A literal GUID AppId was not found in installer.iss.")
    return "{" + str(uuid.UUID(match.group(1))).upper() + "}"


def uninstall_entries(app_id: str) -> list[dict]:
    """Check both machine/user hives and views, including an older installation."""
    import winreg

    entries = []
    key_name = UNINSTALL_ROOT + "\\" + app_id + "_is1"
    for hive_name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
        for view_name, view in (("64", winreg.KEY_WOW64_64KEY), ("32", winreg.KEY_WOW64_32KEY)):
            try:
                key = winreg.OpenKey(hive, key_name, 0, winreg.KEY_READ | view)
            except FileNotFoundError:
                continue
            except OSError as exc:
                raise VerificationError("Cannot safely inspect the uninstall registry keys.") from exc
            with key:
                try:
                    location = str(winreg.QueryValueEx(key, "InstallLocation")[0])
                except FileNotFoundError:
                    location = ""
                entries.append({"hive": hive_name, "view": view_name, "location": location})
    return entries


def require_fixture_entries(entries: list[dict], install: Path) -> None:
    for entry in entries:
        if entry["hive"] != "HKCU" or not entry["location"] or logical_path(entry["location"]) != install:
            raise VerificationError("The uninstall key does not belong to this fixture; uninstall refused.")


def shortcut_paths() -> dict[str, Path]:
    """Use Windows known folders, including redirected/OneDrive user folders."""
    import ctypes
    from ctypes import wintypes

    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.SHGetFolderPathW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.HANDLE,
                                      wintypes.DWORD, wintypes.LPWSTR]
    shell.SHGetFolderPathW.restype = ctypes.c_long

    def folder(csidl: int) -> Path:
        buffer = ctypes.create_unicode_buffer(32768)
        if shell.SHGetFolderPathW(None, csidl, None, 0, buffer) != 0 or not buffer.value:
            raise VerificationError("Cannot safely resolve the user's Windows shortcut folders.")
        return logical_path(buffer.value)

    group = folder(0x0002) / "Mira Media Downloader"  # CSIDL_PROGRAMS
    return {"start_menu_group": group,
            "start_menu_shortcut": group / "Mira Media Downloader.lnk",
            "desktop_shortcut": folder(0x0010) / "Mira Media Downloader.lnk"}  # CSIDL_DESKTOPDIRECTORY


def guard_shortcuts(paths: dict[str, Path]) -> None:
    # Refusing an existing group also protects an empty/pre-existing folder
    # which Inno might otherwise remove when uninstalling its new shortcut.
    if any(filesystem_path(path).exists() for path in paths.values()):
        raise VerificationError("A Mira Start Menu group or Desktop shortcut already exists. Nothing was installed; use a clean Windows account for this test.")


def manifest_entries(bundle: Path) -> list[tuple[str, str]]:
    manifest = bundle / "manifest.sha256"
    if not filesystem_path(manifest).is_file() or filesystem_path(manifest).is_symlink():
        raise VerificationError("Bundle manifest.sha256 is missing or is a link.")
    entries = []
    seen = set()
    for line in filesystem_path(manifest).read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if not match:
            raise VerificationError("Malformed bundle manifest line.")
        expected, filename = match.groups()
        relative = PurePosixPath(filename.replace("\\", "/"))
        if relative.is_absolute() or any(part in {".", ".."} or ":" in part for part in relative.parts):
            raise VerificationError("Unsafe bundle manifest path.")
        name = relative.as_posix()
        if name.casefold() in seen or name.casefold() == "manifest.sha256" or not relative.parts:
            raise VerificationError("Duplicate or invalid bundle manifest path.")
        seen.add(name.casefold())
        target = logical_path(bundle / name)
        if not target.is_relative_to(bundle) or not filesystem_path(target).is_file():
            raise VerificationError("Bundle manifest references a missing or external file.")
        entries.append((expected.lower(), name))
    if not entries or "miramediadownloader.exe" not in seen:
        raise VerificationError("Bundle manifest does not contain the application.")
    actual = {name.casefold() for name in file_names(bundle) if name.casefold() != "manifest.sha256"}
    if actual != seen:
        raise VerificationError("Bundle manifest does not cover the exact source file set.")
    return entries


def check_hashes(root: Path, entries: list[tuple[str, str]]) -> int:
    total = 0
    for expected, name in entries:
        path = logical_path(root / name)
        if not path.is_relative_to(root) or not filesystem_path(path).is_file() or digest(path) != expected:
            raise VerificationError(f"Manifest verification failed for {name}.")
        total += filesystem_path(path).stat().st_size
    return total


def run_process(command: list[str], label: str, fixture: Path, timeout: float,
                environment: dict[str, str] | None = None) -> dict:
    stdout = fixture / (label + "-stdout.log")
    stderr = fixture / (label + "-stderr.log")
    started = time.monotonic()
    with filesystem_path(stdout).open("wb") as output, filesystem_path(stderr).open("wb") as errors:
        process = subprocess.Popen(command, stdout=output, stderr=errors,
                                   stdin=subprocess.DEVNULL, cwd=fixture, env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Only terminate this specific child process tree created above.
            # Do not match names or touch a pre-existing Mira/Qt process.
            if process.poll() is None:
                subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32" / "taskkill.exe"),
                                "/PID", str(process.pid), "/T", "/F"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)
            raise VerificationError(f"{label} timed out; its own process tree was terminated.") from None
    return {"exit_code": code, "seconds": round(time.monotonic() - started, 2),
            "actual_process_exited": True, "stdout_log": str(stdout), "stderr_log": str(stderr)}


def uninstall_fixture(app_id: str, install: Path, fixture: Path, timeout: float,
                      shortcuts: dict[str, Path] | None = None) -> dict:
    # These guards run before invoking the only removal operation in this script.
    task_path(install, "Fixture install directory")
    if install.parent != fixture or install.name != "installed":
        raise VerificationError("Unexpected fixture install directory; uninstall refused.")
    entries = uninstall_entries(app_id)
    require_fixture_entries(entries, install)
    uninstallers = list(filesystem_path(install / "uninstall").glob("unins*.exe"))
    if len(uninstallers) != 1:
        raise VerificationError("Exactly one fixture uninstaller is required for safe cleanup.")
    uninstaller = logical_path(uninstallers[0])
    if not uninstaller.is_relative_to(install) or not filesystem_path(uninstaller).is_file():
        raise VerificationError("Fixture uninstaller path is invalid.")
    result = run_process([str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                          "/LOG=" + str(fixture / "uninstall.log")],
                         "uninstall", fixture, timeout)
    if result["exit_code"] != 0:
        raise VerificationError("Silent fixture uninstall returned a nonzero exit code.")
    deadline = time.monotonic() + 15
    while True:
        remaining = list(file_names(install))
        keys = uninstall_entries(app_id)
        shortcuts_removed = not shortcuts or not any(filesystem_path(path).exists() for path in shortcuts.values())
        if not remaining and not keys and shortcuts_removed:
            break
        if time.monotonic() >= deadline:
            raise VerificationError("Fixture uninstall left application files, its uninstall key or newly created shortcuts.")
        time.sleep(0.25)
    # Do not recursively delete anything. Inno normally removes the empty root;
    # an empty root is harmless and recorded separately if it remains.
    result.update({"registry_key_removed": True, "installed_files_removed": True,
                   "install_directory_removed": not filesystem_path(install).exists()})
    if shortcuts:
        result.update({"start_menu_shortcut_removed": True, "start_menu_group_removed": True,
                       "desktop_shortcut_absent": True})
    return result


def verify(args: argparse.Namespace, receipt: dict) -> None:
    if sys.platform != "win32":
        raise VerificationError("This installer smoke test must run on Windows.")
    setup = task_path(args.setup, "Installer")
    bundle = task_path(args.bundle, "Source bundle")
    if not filesystem_path(setup).is_file() or setup.suffix.casefold() != ".exe" or not filesystem_path(bundle).is_dir():
        raise VerificationError("Supply an existing installer EXE and complete source bundle.")
    app_id = installer_app_id()
    receipt.update({"setup": str(setup), "setup_sha256": digest(setup),
                    "setup_bytes": filesystem_path(setup).stat().st_size, "bundle": str(bundle), "app_id": app_id})
    receipt["stage"] = "preexisting_install_guard"
    if uninstall_entries(app_id):
        raise VerificationError("A Mira installation already has this AppId. Nothing was installed or uninstalled; use a clean Windows account for this test.")
    receipt["preexisting_uninstall_key_absent"] = True
    shortcuts = shortcut_paths()
    guard_shortcuts(shortcuts)
    receipt["preexisting_mira_shortcuts_and_group_absent"] = True
    entries = manifest_entries(bundle)
    receipt["stage"] = "source_manifest"
    receipt["bundle_bytes"] = check_hashes(bundle, entries)
    receipt["manifest_files"] = len(entries)
    fixture = task_path(logical_path(args.out).parent / ("fixture-" + uuid.uuid4().hex), "Fixture")
    filesystem_path(fixture).mkdir(exist_ok=False)
    install = task_path(fixture / "installed", "Fixture install directory")
    receipt["fixture"] = str(fixture)
    receipt["install_directory"] = str(install)
    receipt["fixture_created_new"] = True
    legacy_core = getattr(args, "legacy_core", None)
    if legacy_core is not None:
        legacy_source = task_path(legacy_core, "Known legacy Core")
        legacy_hash = "fe714e03557ad7fed35b45c115609114ccaac8d1224cf9929df9c62a6742c113"
        if digest(legacy_source) != legacy_hash:
            raise VerificationError("The legacy fixture must be the verified1.4.1 Core binary.")
        filesystem_path(install).mkdir(exist_ok=False)
        shutil.copyfile(filesystem_path(legacy_source), filesystem_path(install / "MiraMediaDownloaderCore.exe"))
        receipt["legacy_root_core"] = {"seeded_known_1_4_1_copy_only":True,"sha256":legacy_hash}
    # Recheck immediately before setup so an existing user installation is never
    # silently redirected/updated by Inno's stable AppId handling.
    if uninstall_entries(app_id):
        raise VerificationError("A Mira uninstall key appeared before setup; installation refused.")
    guard_shortcuts(shortcuts)
    setup_started = False
    failure = None
    try:
        receipt["stage"] = "install"
        setup_started = True
        receipt["install"] = run_process([
            str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-", "/NORESTART",
            "/NOCLOSEAPPLICATIONS", "/NOICONS", "/TASKS=", "/DIR=" + str(install),
            "/LOG=" + str(fixture / "install.log")], "install", fixture, args.setup_timeout)
        if receipt["install"]["exit_code"] != 0:
            raise VerificationError("Silent fixture installation returned a nonzero exit code.")
        current = uninstall_entries(app_id)
        if not current:
            raise VerificationError("Installer did not create its per-user uninstall key.")
        require_fixture_entries(current, install)
        receipt["new_uninstall_key_matches_fixture"] = True
        receipt["uninstall_registry_views"] = [entry["hive"] + "/" + entry["view"] for entry in current]
        receipt["start_menu_shortcut_created"] = filesystem_path(shortcuts["start_menu_shortcut"]).is_file()
        if filesystem_path(shortcuts["desktop_shortcut"]).exists():
            raise VerificationError("Installer created a Desktop shortcut despite the empty task selection.")
        receipt["desktop_shortcut_absent_after_install"] = True
        receipt["stage"] = "installed_manifest"
        if legacy_core is not None:
            removed = not filesystem_path(install / "MiraMediaDownloaderCore.exe").exists()
            receipt["legacy_root_core"]["obsolete_executable_removed_after_install"] = removed
            if not removed:
                raise VerificationError("Recognized legacy root Core was not retired after installation.")
        installed_bytes = check_hashes(install, entries)
        if digest(install / "manifest.sha256") != digest(bundle / "manifest.sha256"):
            raise VerificationError("Installed manifest differs from the source bundle.")
        installed_files = {name.casefold() for name in file_names(install)
                           if PurePosixPath(name).parts[0].casefold() != "uninstall"}
        expected_files = {name.casefold() for _, name in entries} | {"manifest.sha256"}
        if installed_files != expected_files:
            raise VerificationError("Installed payload has missing or unexpected files.")
        receipt["installed_manifest"] = {"passed": True, "files": len(entries),
                                           "bytes": installed_bytes, "manifest_identical": True,
                                           "exact_payload_file_set": True}
        receipt["stage"] = "installed_design_probe"
        probe = task_path(fixture / "design-probe", "Design probe")
        filesystem_path(probe).mkdir(exist_ok=False)
        environment = dict(os.environ)
        environment.update({"APPDATA": str(probe / "isolated-roaming"),
                            "LOCALAPPDATA": str(probe / "isolated-local"),
                            "MIRA_SESSION_DIR": str(probe / "isolated-empty-vault"),
                            "PYTHONIOENCODING": "utf-8"})
        receipt["design_process"] = run_process([str(install / "MiraMediaDownloader.exe"),
                                                   "--design-probe", str(probe)],
                                                  "design-probe", fixture, args.probe_timeout, environment)
        if receipt["design_process"]["exit_code"] != 0:
            raise VerificationError("Installed EXE design probe returned a nonzero exit code.")
        result = json.loads(filesystem_path(probe / "design-probe.json").read_text(encoding="utf-8-sig"))
        if not result.get("passed") or result.get("errors") or result.get("network_requests") != 0 or result.get("real_user_cookies_accessed") is not False:
            raise VerificationError("Installed design probe did not pass its offline/isolation checks.")
        checks = result.get("checks")
        if not isinstance(checks, dict) or not checks or not all(value is True for value in checks.values()):
            raise VerificationError("Installed design probe has missing or failed acceptance checks.")
        receipt["installed_design_probe"] = {"passed": True, "checks": len(checks),
                                               "receipt": str(probe / "design-probe.json"),
                                               "actual_process_exit_code": 0,
                                               "network_requests": 0, "real_user_cookies_accessed": False}
    except Exception as exc:
        failure = exc
    finally:
        if setup_started:
            receipt["stage"] = "uninstall"
            try:
                receipt["uninstall"] = uninstall_fixture(app_id, install, fixture, args.uninstall_timeout, shortcuts)
            except Exception as exc:
                receipt["cleanup_error"] = str(exc)
                if failure is None:
                    failure = exc
    if failure is not None:
        raise failure
    receipt.update({"passed": True, "stage": "complete", "actual_user_cookies_accessed": False,
                    "network_requests_in_design_probe": 0, "forced_process_termination": False,
                    "installation_silent": True, "desktop_shortcuts_disabled": True,
                    "start_menu_shortcut_removed": True,
                    "automatic_application_closing_disabled": True,
                    "fixture_evidence_preserved": True,
                    "windows_extended_length_filesystem_paths": os.name == "nt"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", required=True, type=Path)
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--legacy-core", type=Path, help="Seed a copy of the verified1.4.1 Core to test obsolete-file migration.")
    parser.add_argument("--setup-timeout", type=float, default=300)
    parser.add_argument("--probe-timeout", type=float, default=75)
    parser.add_argument("--uninstall-timeout", type=float, default=120)
    args = parser.parse_args()
    if min(args.setup_timeout, args.probe_timeout, args.uninstall_timeout) <= 0:
        parser.error("Timeouts must be positive.")
    try:
        output = task_path(args.out, "Receipt")
        if output.suffix.casefold() != ".json" or filesystem_path(output).exists():
            raise VerificationError("Use a new JSON receipt path; existing QA evidence is never overwritten.")
        filesystem_path(output.parent).mkdir(parents=True, exist_ok=True)
    except VerificationError as exc:
        parser.error(str(exc))
    receipt = {"passed": False, "stage": "preflight", "setup_sha256": "",
               "started_utc": datetime.now(timezone.utc).isoformat(),
               "script": str(Path(__file__).resolve()), "task_workspace": str(TASK_ROOT)}
    started = time.monotonic()
    try:
        verify(args, receipt)
    except Exception as exc:
        receipt["error"] = type(exc).__name__ + ": " + str(exc)
    receipt["elapsed_seconds"] = round(time.monotonic() - started, 2)
    filesystem_path(output).write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": receipt["passed"], "receipt": str(output),
                      "stage": receipt["stage"], "error": receipt.get("error", "")}, ensure_ascii=False))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
