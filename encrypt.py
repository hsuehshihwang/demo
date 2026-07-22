#!/usr/bin/env python3
"""
AES-256-CBC encryption tool for MP4 video files.
Encrypts .mp4 files into .enc files that can be decrypted in the browser.

Usage:
    python encrypt.py video.mp4                 # encrypt with default password (TestVideo + today)
    python encrypt.py video.mp4 -p MyPassword   # encrypt with custom password
    python encrypt.py *.mp4                     # encrypt multiple files
    python encrypt.py -d videos/                # encrypt all .mp4 files in a directory

Output: {filename}.mp4.enc (IV prepended as first 16 bytes)
"""

import argparse
import hashlib
import os
import sys
import glob
from datetime import datetime


def load_env():
    """Load .env file into environment."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


load_env()

try:
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
    from cryptography.hazmat.primitives import hashes as asym_hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from os import urandom as get_random_bytes
    HAS_CRYPTOGRAPHY = True
except ImportError:
    HAS_CRYPTOGRAPHY = False

try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    from Crypto.Random import get_random_bytes
    HAS_PYTODOME = True
except ImportError:
    HAS_PYTODOME = False

BLOCK_SIZE = 16
SALT = b"VideoEncrypt_v1"


def derive_key(password: str) -> bytes:
    """Derive a 32-byte AES key from password using PBKDF2."""
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), SALT, 100000, dklen=32)


def pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def encrypt_file_cryptography(input_path: str, output_path: str, password: str):
    """Encrypt a file using the cryptography library."""
    key = derive_key(password)
    iv = get_random_bytes(BLOCK_SIZE)

    with open(input_path, "rb") as f:
        plaintext = f.read()

    padded = pkcs7_pad(plaintext)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()

    with open(output_path, "wb") as f:
        f.write(iv + ciphertext)


def encrypt_file_pycryptodome(input_path: str, output_path: str, password: str):
    """Encrypt a file using PyCryptodome."""
    key = derive_key(password)
    iv = get_random_bytes(BLOCK_SIZE)

    with open(input_path, "rb") as f:
        plaintext = f.read()

    cipher = AES.new(key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext, BLOCK_SIZE))

    with open(output_path, "wb") as f:
        f.write(iv + ciphertext)


def encrypt_file(input_path: str, output_path: str, password: str):
    """Encrypt a file using available library."""
    if HAS_CRYPTOGRAPHY:
        encrypt_file_cryptography(input_path, output_path, password)
    elif HAS_PYTODOME:
        encrypt_file_pycryptodome(input_path, output_path, password)
    else:
        print("ERROR: No encryption library found. Install one of:")
        print("  pip install cryptography")
        print("  pip install pycryptodome")
        sys.exit(1)


def get_output_path(input_path: str) -> str:
    """Generate output path: video.mp4 -> video.mp4.enc"""
    return input_path + ".enc"


def process_file(input_path: str, password: str):
    """Encrypt a single file."""
    if not os.path.exists(input_path):
        print(f"  SKIP: {input_path} not found")
        return False

    output_path = get_output_path(input_path)
    file_size = os.path.getsize(input_path)

    print(f"  Encrypting: {input_path} ({file_size / 1024 / 1024:.1f} MB)")
    encrypt_file(input_path, output_path, password)
    enc_size = os.path.getsize(output_path)
    print(f"  Output:     {output_path} ({enc_size / 1024 / 1024:.1f} MB)")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Encrypt MP4 files for browser playback",
        epilog="Example: python encrypt.py video1.mp4 video2.mp4 (uses default key 'TestVideo')"
    )
    parser.add_argument("files", nargs="*", help="MP4 files to encrypt")
    parser.add_argument("-d", "--directory", help="Encrypt all .mp4 files in directory")
    parser.add_argument("-p", "--password", help="Encryption password (default: TestVideo + today's date)")
    parser.add_argument("-o", "--output-dir", help="Output directory (default: same as input)")
    args = parser.parse_args()

    if args.password:
        password = args.password
    else:
        password = os.environ.get("VIDEO_KEY", "")
        if not password:
            password = input("Enter encryption key: ").strip()
            if not password:
                error("Key cannot be empty")

    print(f"Password: {password}")
    print(f"Key hash: {hashlib.sha256(derive_key(password)).hexdigest()[:16]}...")

    if not HAS_CRYPTOGRAPHY and not HAS_PYTODOME:
        print("\nERROR: No encryption library found. Install one:")
        print("  pip install cryptography")
        print("  pip install pycryptodome")
        sys.exit(1)

    lib = "cryptography" if HAS_CRYPTOGRAPHY else "pycryptodome"
    print(f"Library:  {lib}\n")

    files_to_encrypt = []

    if args.files:
        files_to_encrypt.extend(args.files)

    if args.directory:
        pattern = os.path.join(args.directory, "*.mp4")
        files_to_encrypt.extend(glob.glob(pattern))
        pattern2 = os.path.join(args.directory, "**", "*.mp4")
        files_to_encrypt.extend(glob.glob(pattern2, recursive=True))

    if not files_to_encrypt:
        parser.print_help()
        print("\nNo files specified. Use --directory or provide file paths.")
        sys.exit(1)

    files_to_encrypt = sorted(set(files_to_encrypt))
    success = 0

    for input_path in files_to_encrypt:
        output_path = get_output_path(input_path)

        if args.output_dir:
            os.makedirs(args.output_dir, exist_ok=True)
            output_path = os.path.join(args.output_dir, os.path.basename(output_path))

        if process_file(input_path, password):
            success += 1
        print()

    print(f"Done: {success}/{len(files_to_encrypt)} files encrypted")

    generate_manifest(args.output_dir or ".")


def generate_manifest(base_dir: str):
    """Write videos/videos.json listing all .enc files."""
    enc_files = sorted(glob.glob(os.path.join(base_dir, "videos", "*.enc")))
    entries = []
    seen = set()
    for f in enc_files:
        name = os.path.basename(f)
        if name not in seen:
            seen.add(name)
            size = os.path.getsize(f)
            entries.append({"file": name, "size": size})
    manifest_path = os.path.join(base_dir, "videos", "videos.json")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    import json
    with open(manifest_path, "w") as fh:
        json.dump(entries, fh, indent=2)
    print(f"Manifest: {manifest_path} ({len(entries)} videos)")


if __name__ == "__main__":
    main()
