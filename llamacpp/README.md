# llamacpp Service

This directory contains the entrypoint script and configuration for the `llamacpp` service, which runs [llama.cpp server](https://github.com/ggml-org/llama.cpp) as part of the news48 Docker Compose stack.

## Docker Image Selection

The service uses the official llama.cpp Docker images from the GitHub Container Registry. Select the image variant that matches your hardware:

| Image Tag | Use Case |
|-----------|----------|
| `server-cuda13` | NVIDIA GPUs with CUDA 13 (recommended for modern GPUs) |
| `server-cuda12` | NVIDIA GPUs with CUDA 12 |
| `server-rocm` | AMD GPUs with ROCm |
| `server-intel` | Intel GPUs |
| `server-cpu` | CPU-only (no GPU acceleration) |

The default image in `docker-compose.yml` is `ghcr.io/ggml-org/llama.cpp:server-cuda13`. To change it, set the `image` field in your compose file or override it in a custom compose file.

See the [llama.cpp Docker docs](https://github.com/ggml-org/llama.cpp/blob/master/docs/docker.md) for more details on image variants and build options.

## Model Configuration

The model is auto-downloaded from HuggingFace on first start. Configure the model via environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLAMACPP_MODEL_REPO` | HuggingFace repository (owner/repo) | `mradermacher/claude-oss-i1-GGUF` |
| `LLAMACPP_MODEL_FILE` | Model filename in the repo | `claude-oss-i1.Q6_K.gguf` |

The download URL is constructed as: `https://huggingface.co/{repo}/resolve/main/{file}`

## Server Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `LLAMACPP_CTX_SIZE` | Context window size (KV-cache allocation) | `131072` |
| `LLAMACPP_PORT` | Server port | `8080` |
| `LLAMACPP_N_GPU_LAYERS` | Number of layers to offload to GPU (`999` = all) | `999` |
| `LLAMACPP_PARALLEL` | Number of parallel sequences | `4` |
| `LLAMACPP_THREADS` | Number of CPU threads | `8` |
| `LLAMACPP_CACHE_TYPE_K` | KV cache type for K | `q8_0` |
| `LLAMACPP_CACHE_TYPE_V` | KV cache type for V | `q8_0` |
| `LLAMACPP_FLASH_ATTN` | Enable flash attention (`on`/`off`) | `on` |

## Prerequisites

- **NVIDIA Container Toolkit** installed on the host for GPU passthrough
- Sufficient disk space for the model (~10-15 GB for Q6_K quantization)
- Sufficient GPU VRAM for the model at the configured context size
