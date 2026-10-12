"""
Asset Downloader and Checksum Verifier.
Ensures zero redundant downloads: checks existing files and verifies hashes before downloading.
"""

import hashlib
import os
import shutil
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = PROJECT_ROOT / "models"
TTS_MODELS_DIR = MODELS_DIR / "tts"
STT_MODELS_DIR = MODELS_DIR / "stt"
BIN_DIR = PROJECT_ROOT / "bin" / "llama.cpp"

# Asset manifests with exact upstream URLs, sizes, and SHA-256 hashes
ASSETS = {
    "llama_cuda_bin": {
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11429/llama-b11429-bin-win-cuda-12.4-x64.zip",
        "expected_sha256": "dd6df685c1024e6aa55ca55ad35038692d5e284d4dc895e7a646c3245d3d14ff",
        "expected_size": 264478423,
        "dest_dir": BIN_DIR,
        "marker_file": BIN_DIR / "llama-server.exe",
    },
    "llama_cudart": {
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b11429/cudart-llama-bin-win-cuda-12.4-x64.zip",
        "expected_sha256": "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6",
        "expected_size": 391443627,
        "dest_dir": BIN_DIR,
        "marker_file": BIN_DIR / "cudart64_12.dll",
    },
    "qwen3_1.7b_gguf": {
        "url": "https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_K_M.gguf",
        "expected_sha256": "d2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5",
        "expected_size": 1282439264,
        "target_file": MODELS_DIR / "Qwen3-1.7B-Q4_K_M.gguf",
    },
    "piper_voice_onnx": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "expected_sha256": "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
        "expected_size": 63201294,
        "target_file": TTS_MODELS_DIR / "en_US-lessac-medium.onnx",
    },
    "piper_voice_json": {
        "url": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "expected_sha256": "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
        "expected_size": 4885,
        "target_file": TTS_MODELS_DIR / "en_US-lessac-medium.onnx.json",
    },
}



def calculate_sha256(filepath: Path) -> str:
    """Computes SHA-256 hash in 8MB chunks to conserve RAM."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8 * 1024 * 1024):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def download_with_progress(url: str, dest_file: Path, expected_size: int | None = None, max_retries: int = 15):
    """Downloads a file with HTTP Range resume support and automatic retry."""
    temp_file = dest_file.with_suffix(dest_file.suffix + ".tmp")
    dest_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"[*] Downloading: {dest_file.name}")
    print(f"    Source: {url}")

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    for attempt in range(1, max_retries + 1):
        existing_bytes = temp_file.stat().st_size if temp_file.exists() else 0
        if expected_size and existing_bytes >= expected_size:
            break

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AI-Assistant-Setup/1.0",
        }
        if existing_bytes > 0:
            headers["Range"] = f"bytes={existing_bytes}-"
            print(f"\n[*] Resuming download from {existing_bytes / (1024*1024):.1f} MB (attempt {attempt}/{max_retries})...")

        req = urllib.request.Request(url, headers=headers)

        try:
            with opener.open(req, timeout=30) as resp:
                status = getattr(resp, "status", getattr(resp, "code", 200))
                # 206 Partial Content means resume supported; 200 means full stream from start
                mode = "ab" if (existing_bytes > 0 and status == 206) else "wb"
                if mode == "wb":
                    existing_bytes = 0

                total_size = expected_size or (int(resp.headers.get("Content-Length", 0)) + existing_bytes)
                block_size = 1024 * 1024  # 1MB
                downloaded = existing_bytes
                start_time = time.time()

                with open(temp_file, mode) as out_f:
                    while chunk := resp.read(block_size):
                        out_f.write(chunk)
                        downloaded += len(chunk)
                        elapsed = max(time.time() - start_time, 0.001)
                        speed_mb = ((downloaded - existing_bytes) / (1024 * 1024)) / elapsed

                        pct = (downloaded / total_size) * 100 if total_size > 0 else 0
                        sys.stdout.write(
                            f"\r    Progress: {downloaded / (1024*1024):.1f}/{total_size / (1024*1024):.1f} MB "
                            f"({pct:.1f}%) - Speed: {speed_mb:.2f} MB/s"
                        )
                        sys.stdout.flush()

            print()
            current_size = temp_file.stat().st_size
            if expected_size and current_size < expected_size:
                print(f"[!] Incomplete stream: received {current_size / (1024*1024):.1f}/{expected_size / (1024*1024):.1f} MB. Reconnecting...")
                time.sleep(2)
                continue
            else:
                break
        except Exception as e:
            print(f"\n[!] Network exception during stream: {e}. Retrying in 3s...")
            time.sleep(3)

    final_size = temp_file.stat().st_size if temp_file.exists() else 0
    if expected_size and final_size != expected_size:
        raise IOError(f"Failed to download complete file after {max_retries} attempts: {final_size}/{expected_size} bytes.")

    temp_file.replace(dest_file)
    print(f"[+] Download complete: {dest_file.name}")


def setup_llama_cpp(force: bool = False):
    """Downloads and extracts llama.cpp Windows CUDA binaries."""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    server_exe = ASSETS["llama_cuda_bin"]["marker_file"]
    cudart_dll = ASSETS["llama_cudart"]["marker_file"]

    if not force and server_exe.exists() and cudart_dll.exists():
        print(f"[OK] llama.cpp runtime already installed in {BIN_DIR}. Skipping download.")
        return

    tmp_dir = PROJECT_ROOT / "scratch" / "downloads"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    for asset_key in ["llama_cuda_bin", "llama_cudart"]:
        asset = ASSETS[asset_key]
        zip_path = tmp_dir / f"{asset_key}.zip"

        # Check if zip already exists with valid hash
        needs_download = True
        if zip_path.exists():
            print(f"[*] Checking existing archive {zip_path.name}...")
            actual_hash = calculate_sha256(zip_path)
            if actual_hash == asset["expected_sha256"]:
                print(f"[OK] Existing archive {zip_path.name} verified with valid SHA-256.")
                needs_download = False
            else:
                print(f"[!] Existing archive hash mismatch. Re-downloading.")
                zip_path.unlink()

        if needs_download:
            download_with_progress(asset["url"], zip_path, asset["expected_size"])
            print("[*] Verifying SHA-256 hash...")
            actual_hash = calculate_sha256(zip_path)
            if actual_hash != asset["expected_sha256"]:
                zip_path.unlink()
                raise ValueError(
                    f"Checksum mismatch for {asset_key}!\nExpected: {asset['expected_sha256']}\nGot: {actual_hash}"
                )
            print("[OK] Checksum verified.")

        print(f"[*] Extracting {zip_path.name} into {BIN_DIR}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(BIN_DIR)

        # Cleanup zip to save space
        zip_path.unlink()

    print(f"[OK] llama.cpp runtime successfully installed at {BIN_DIR}")


def setup_model(force: bool = False):
    """Downloads and verifies the Qwen3-1.7B-Q4_K_M model."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    asset = ASSETS["qwen3_1.7b_gguf"]
    target_file = asset["target_file"]

    if not force and target_file.exists():
        actual_size = target_file.stat().st_size
        if actual_size == asset["expected_size"]:
            print(f"[OK] Model already exists: {target_file.name} (size: {actual_size} bytes).")
            print("     Verifying SHA-256 checksum...")
            actual_hash = calculate_sha256(target_file)
            if actual_hash == asset["expected_sha256"]:
                print(f"[OK] Model checksum valid: {actual_hash}. Skipping download.")
                return
            else:
                print(f"[!] Existing model checksum mismatch. Re-downloading.")
                target_file.unlink()
        else:
            print(f"[!] Existing model size mismatch ({actual_size} != {asset['expected_size']}). Re-downloading.")
            target_file.unlink()

    download_with_progress(asset["url"], target_file, asset["expected_size"])
    print("[*] Verifying SHA-256 hash of downloaded model...")
    actual_hash = calculate_sha256(target_file)
    if actual_hash != asset["expected_sha256"]:
        target_file.unlink()
        raise ValueError(
            f"Model checksum mismatch!\nExpected: {asset['expected_sha256']}\nGot: {actual_hash}"
        )
    print(f"[OK] Model verified successfully: {actual_hash}")


def setup_tts(force: bool = False):
    """Downloads and verifies the Piper TTS voice model and configuration."""
    TTS_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    for asset_key in ("piper_voice_onnx", "piper_voice_json"):
        asset = ASSETS[asset_key]
        target_file = asset["target_file"]

        if not force and target_file.exists():
            actual_size = target_file.stat().st_size
            if actual_size == asset["expected_size"]:
                print(f"[OK] Voice asset exists: {target_file.name} (size: {actual_size} bytes).")
                print("     Verifying SHA-256 checksum...")
                actual_hash = calculate_sha256(target_file)
                if actual_hash == asset["expected_sha256"]:
                    print(f"[OK] Voice asset checksum valid: {actual_hash}. Skipping download.")
                    continue
                else:
                    print(f"[!] Existing asset checksum mismatch. Re-downloading: {target_file.name}")
                    target_file.unlink()
            else:
                print(f"[!] Existing asset size mismatch ({actual_size} != {asset['expected_size']}). Re-downloading.")
                target_file.unlink()

        download_with_progress(asset["url"], target_file, asset["expected_size"])
        print(f"[*] Verifying SHA-256 hash of {target_file.name}...")
        actual_hash = calculate_sha256(target_file)
        if actual_hash != asset["expected_sha256"]:
            target_file.unlink()
            raise ValueError(
                f"Asset checksum mismatch for {target_file.name}!\nExpected: {asset['expected_sha256']}\nGot: {actual_hash}"
            )
        print(f"[OK] {target_file.name} verified successfully: {actual_hash}")
    print(f"[OK] Piper TTS voice assets ready at {TTS_MODELS_DIR}")


def main():
    force = "--force" in sys.argv
    download_tts = "--tts" in sys.argv or "--voice" in sys.argv or "--all" in sys.argv
    print("==================================================")
    print("   AI Assistant: Local Assets Setup & Verifier    ")
    print("==================================================")
    print(f"Target Project Directory: {PROJECT_ROOT}")

    try:
        setup_llama_cpp(force=force)
        setup_model(force=force)
        if download_tts:
            setup_tts(force=force)
        print("\n[SUCCESS] All requested assets are verified and ready for offline operation.")
    except Exception as e:
        print(f"\n[ERROR] Setup failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

