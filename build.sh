#!/bin/bash
# =============================================================================
# build.sh - Master build script for encrypted video site
#
# Usage:
#   ./build.sh                          # interactive: prompts for key
#   ./build.sh --key MySecret           # non-interactive
#   ./build.sh --encrypt videos/*.mp4   # encrypt files + rebuild
#   ./build.sh --rebuild                # just regenerate videos.json + MD5
#   ./build.sh --decrypt videos/x.mp4.enc  # decrypt a file
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"
JS_FILE="$SCRIPT_DIR/script.js"
PY_ENCRYPT="$SCRIPT_DIR/encrypt.py"
VIDEOS_DIR="$SCRIPT_DIR/videos"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# --- Load key from .env ---
load_env() {
    if [ -f "$ENV_FILE" ]; then
        export $(grep -E '^VIDEO_KEY=' "$ENV_FILE" | xargs)
    fi
}

# --- Compute MD5 hash ---
compute_md5() {
    python3 -c "import hashlib; print(hashlib.md5('$1'.encode()).hexdigest())"
}

# --- Update MD5_HASH in script.js ---
update_js_md5() {
    local hash="$1"
    if [ ! -f "$JS_FILE" ]; then
        error "script.js not found at $JS_FILE"
    fi

    # Replace the MD5_HASH line
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s|const MD5_HASH = \"[a-f0-9]*\";|const MD5_HASH = \"$hash\";|" "$JS_FILE"
    else
        sed -i "s|const MD5_HASH = \"[a-f0-9]*\";|const MD5_HASH = \"$hash\";|" "$JS_FILE"
    fi

    ok "Updated MD5_HASH in script.js to $hash"
}

# --- Generate videos.json manifest ---
generate_manifest() {
    python3 -c "
import glob, json, os

videos_dir = '$VIDEOS_DIR'
enc_files = sorted(glob.glob(os.path.join(videos_dir, '*.enc')))
entries = []
seen = set()
for f in enc_files:
    name = os.path.basename(f)
    if name not in seen:
        seen.add(name)
        size = os.path.getsize(f)
        entries.append({'file': name, 'size': size})

manifest = os.path.join(videos_dir, 'videos.json')
with open(manifest, 'w') as fh:
    json.dump(entries, fh, indent=2)
print(f'  Generated {manifest} with {len(entries)} video(s)')
"
}

# --- Encrypt files ---
encrypt_files() {
    local key="$1"
    shift
    local files=("$@")

    if [ ${#files[@]} -eq 0 ]; then
        error "No files specified. Usage: ./build.sh --encrypt videos/*.mp4"
    fi

    info "Encrypting ${#files[@]} file(s)..."
    for f in "${files[@]}"; do
        if [ ! -f "$f" ]; then
            warn "Skipping $f (not found)"
            continue
        fi
        python3 "$PY_ENCRYPT" "$f" -p "$key"
    done
}

# --- Decrypt a file ---
decrypt_file() {
    local enc_file="$1"
    local key="$2"
    local output="${3:-${enc_file%.enc}}"

    if [ ! -f "$enc_file" ]; then
        error "File not found: $enc_file"
    fi

    info "Decrypting $enc_file..."
    python3 -c "
import hashlib
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

key = hashlib.pbkdf2_hmac('sha256', '$key'.encode(), b'VideoEncrypt_v1', 100000, dklen=32)

with open('$enc_file', 'rb') as f:
    data = f.read()

iv = data[:16]
ciphertext = data[16:]
cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
decryptor = cipher.decryptor()
plain = decryptor.update(ciphertext) + decryptor.finalize()

# PKCS7 unpad
pad_len = plain[-1]
plain = plain[:-pad_len]

with open('$output', 'wb') as f:
    f.write(plain)

print(f'  Decrypted to $output ({len(plain)} bytes)')
"
    ok "Decrypted: $output"
}

# --- Full rebuild ---
full_build() {
    local key="$1"

    info "Using key: ${key:0:3}***$(echo "$key" | tail -c 3)"
    echo ""

    # 1. Update MD5 hash in script.js
    info "Step 1: Updating MD5 hash..."
    local md5_hash
    md5_hash=$(compute_md5 "$key")
    update_js_md5 "$md5_hash"
    echo ""

    # 2. Generate videos.json manifest
    info "Step 2: Generating videos.json..."
    mkdir -p "$VIDEOS_DIR"
    generate_manifest
    echo ""

    ok "Build complete!"
    echo ""
    echo -e "${CYAN}Summary:${NC}"
    echo -e "  Key MD5:   $md5_hash"
    echo -e "  Videos:    $(ls "$VIDEOS_DIR"/*.enc 2>/dev/null | wc -l | tr -d ' ') encrypted file(s)"
    echo -e "  Manifest:  $VIDEOS_DIR/videos.json"
    echo ""
    echo -e "Daily password: ${key}$(date +%Y%m%d)"
}

# --- Parse args ---
ACTION="rebuild"
KEY=""
FILES=()
DECRYPT_FILE=""
DECRYPT_OUTPUT=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --key)
            KEY="$2"
            shift 2
            ;;
        --encrypt)
            ACTION="encrypt"
            shift
            while [[ $# -gt 0 && ! "$1" =~ ^-- ]]; do
                FILES+=("$1")
                shift
            done
            ;;
        --decrypt)
            ACTION="decrypt"
            DECRYPT_FILE="$2"
            shift 2
            if [[ $# -gt 0 && ! "$1" =~ ^-- ]]; then
                DECRYPT_OUTPUT="$1"
                shift
            fi
            ;;
        --rebuild)
            ACTION="rebuild"
            shift
            ;;
        *)
            error "Unknown option: $1"
            ;;
    esac
done

# --- Get key ---
load_env

if [ -z "$KEY" ] && [ -n "${VIDEO_KEY:-}" ]; then
    KEY="$VIDEO_KEY"
fi

if [ -z "$KEY" ]; then
    if [ "$ACTION" = "rebuild" ] || [ "$ACTION" = "encrypt" ]; then
        read -sp "Enter encryption key: " KEY
        echo ""
        if [ -z "$KEY" ]; then
            error "Key cannot be empty"
        fi
    fi
fi

if [ -z "$KEY" ] && [ "$ACTION" = "decrypt" ]; then
    read -sp "Enter decryption key: " KEY
    echo ""
fi

# --- Execute ---
echo ""
case $ACTION in
    rebuild)
        full_build "$KEY"
        ;;
    encrypt)
        encrypt_files "$KEY" "${FILES[@]}"
        echo ""
        info "Regenerating manifest..."
        generate_manifest
        echo ""
        ok "Encrypt + rebuild complete!"
        ;;
    decrypt)
        decrypt_file "$DECRYPT_FILE" "$KEY" "$DECRYPT_OUTPUT"
        ;;
esac
