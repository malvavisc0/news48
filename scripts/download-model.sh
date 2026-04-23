#!/bin/bash
# Download the GGUF model for llama.cpp if not already present.
# Used by the llamacpp-init service so the model is ready before the server starts.

set -euo pipefail

# Configuration from environment variables
MODEL_REPO="${LLAMACPP_MODEL_REPO:-mradermacher/claude-oss-i1-GGUF}"
MODEL_FILE="${LLAMACPP_MODEL_FILE:-claude-oss.i1-Q6_K.gguf}"

MODEL_PATH="/models/${MODEL_FILE}"
HF_URL="https://huggingface.co/${MODEL_REPO}/resolve/main/${MODEL_FILE}"

# Validate that a file starts with the GGUF magic header (0x47 0x47 0x55 0x46)
validate_gguf() {
    local path="$1"
    local magic
    magic=$(head -c 4 "$path" 2>/dev/null | od -A n -t x1 | tr -d ' ')
    if [ "$magic" != "47475546" ]; then
        return 1
    fi
    return 0
}

# Download model if it doesn't exist (or is corrupted)
download_model() {
    if [ -f "$MODEL_PATH" ]; then
        if validate_gguf "$MODEL_PATH"; then
            echo "[$(date -Iseconds)] Model already exists at ${MODEL_PATH}, skipping download."
            return
        fi
        echo "[$(date -Iseconds)] Existing file at ${MODEL_PATH} is not a valid GGUF file (corrupted or incomplete download)."
        echo "[$(date -Iseconds)] Removing corrupted file and re-downloading..."
        rm -f "$MODEL_PATH"
    fi

    echo "[$(date -Iseconds)] Model not found at ${MODEL_PATH}, downloading from HuggingFace..."
    echo "[$(date -Iseconds)] URL: ${HF_URL}"

    mkdir -p /models

    # Verify URL is reachable before downloading (HEAD request with --fail)
    echo "[$(date -Iseconds)] Verifying URL is reachable..."
    HEAD_OPTS=(-s -o /dev/null -w "%{http_code}" -L --head)
    if [ -n "${HF_TOKEN:-}" ]; then
        HEAD_OPTS+=(-H "Authorization: Bearer ${HF_TOKEN}")
    fi
    HTTP_CODE=$(curl "${HEAD_OPTS[@]}" "$HF_URL" 2>/dev/null || true)
    if [ "$HTTP_CODE" != "200" ] && [ "$HTTP_CODE" != "302" ]; then
        echo "[$(date -Iseconds)] ERROR: HuggingFace returned HTTP ${HTTP_CODE} for the model URL."
        echo "[$(date -Iseconds)] URL: ${HF_URL}"
        echo "[$(date -Iseconds)] Possible causes:"
        echo "[$(date -Iseconds)]   - The repo '${MODEL_REPO}' may not exist on HuggingFace"
        echo "[$(date -Iseconds)]   - The file '${MODEL_FILE}' may not exist in the repo"
        echo "[$(date -Iseconds)]   - The model may be gated/private (set HF_TOKEN for auth)"
        echo "[$(date -Iseconds)] Check LLAMACPP_MODEL_REPO and LLAMACPP_MODEL_FILE in your .env file."
        exit 1
    fi

    # Build auth header if HF_TOKEN is set (for gated models)
    CURL_OPTS=(-C - -L --fail -o "$MODEL_PATH")
    if [ -n "${HF_TOKEN:-}" ]; then
        echo "[$(date -Iseconds)] Using HF_TOKEN for authenticated download."
        CURL_OPTS+=(-H "Authorization: Bearer ${HF_TOKEN}")
    fi

    # Download with resume support and --fail to catch HTTP errors
    if ! curl "${CURL_OPTS[@]}" "$HF_URL"; then
        echo "[$(date -Iseconds)] ERROR: curl failed to download the model (HTTP error or network issue)."
        echo "[$(date -Iseconds)] URL: ${HF_URL}"
        echo "[$(date -Iseconds)] Possible causes:"
        echo "[$(date -Iseconds)]   - The repo '${MODEL_REPO}' may not exist on HuggingFace"
        echo "[$(date -Iseconds)]   - The file '${MODEL_FILE}' may not exist in the repo"
        echo "[$(date -Iseconds)]   - The model may be gated/private (set HF_TOKEN for auth)"
        echo "[$(date -Iseconds)] Check LLAMACPP_MODEL_REPO and LLAMACPP_MODEL_FILE in your .env file."
        rm -f "$MODEL_PATH"
        exit 1
    fi

    # Verify download succeeds (non-zero file size)
    if [ ! -s "$MODEL_PATH" ]; then
        echo "[$(date -Iseconds)] ERROR: Downloaded model file is empty."
        rm -f "$MODEL_PATH"
        exit 1
    fi

    # Verify the file is a valid GGUF file (not an HTML redirect or LFS pointer)
    if ! validate_gguf "$MODEL_PATH"; then
        FILE_SIZE=$(stat -c%s "$MODEL_PATH" 2>/dev/null || echo "unknown")
        FILE_HEAD=$(head -c 100 "$MODEL_PATH" 2>/dev/null || echo "")
        echo "[$(date -Iseconds)] ERROR: Downloaded file is not a valid GGUF model (${FILE_SIZE} bytes)."
        echo "[$(date -Iseconds)] File starts with: ${FILE_HEAD}"
        echo "[$(date -Iseconds)] The URL may be incorrect, or the download was interrupted."
        echo "[$(date -Iseconds)] Check LLAMACPP_MODEL_REPO and LLAMACPP_MODEL_FILE settings."
        rm -f "$MODEL_PATH"
        exit 1
    fi

    FILE_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
    echo "[$(date -Iseconds)] Model downloaded successfully (${FILE_SIZE})."
}

download_model
