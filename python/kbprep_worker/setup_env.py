"""
setup_env — post-install hardware detection and auto-configuration.

Detects GPU capability, checks torch CUDA support, and installs CUDA torch
if a compatible NVIDIA GPU is found but torch lacks CUDA support.
"""
import shutil
import subprocess
import sys
import logging

logger = logging.getLogger(__name__)


def check_nvidia_driver():
    """Check if nvidia-smi is available (driver installed)."""
    return shutil.which("nvidia-smi") is not None


def check_torch_cuda():
    """Check if torch has CUDA support enabled."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        return False


def get_gpu_info():
    """Get GPU info if available."""
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            return {
                "available": True,
                "device_name": torch.cuda.get_device_name(0),
                "vram_gb": round(props.total_memory / 1024**3, 1),
                "cuda_version": torch.version.cuda,
                "torch_version": torch.__version__,
            }
    except Exception:
        pass
    return {"available": False}


def detect_device():
    """Detect best available compute device."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"


def setup_gpu(venv_python=None):
    """Main entry: detect GPU, install CUDA torch if needed."""
    python = venv_python or sys.executable
    result = {
        "nvidia_driver": check_nvidia_driver(),
        "torch_cuda": check_torch_cuda(),
        "gpu": get_gpu_info(),
        "device": detect_device(),
        "actions_taken": [],
    }

    if result["nvidia_driver"] and not result["torch_cuda"]:
        logger.info("NVIDIA GPU detected but torch lacks CUDA support. Installing CUDA torch...")
        try:
            subprocess.run(
                [python, "-m", "pip", "install", "torch", "torchvision",
                 "--index-url", "https://download.pytorch.org/whl/cu126"],
                check=True,
                timeout=600,
            )
            result["torch_cuda"] = check_torch_cuda()
            result["gpu"] = get_gpu_info()
            result["device"] = detect_device()
            result["actions_taken"].append("installed_cuda_torch")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            result["actions_taken"].append(f"cuda_install_failed: {e}")

    return result
