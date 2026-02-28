"""
로컬 Whisper STT 서비스
faster-whisper (CTranslate2) 기반, CUDA 가속
RTX 4090에서 large-v3 모델도 1-2초 이내 처리
"""

import io
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Pre-add NVIDIA CUDA DLL paths (pip-installed nvidia-cublas-cu12 etc.)
try:
    import nvidia.cublas
    _cublas_bin = str(Path(nvidia.cublas.__path__[0]) / "bin")
    if _cublas_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _cublas_bin + os.pathsep + os.environ.get("PATH", "")
        # Also add via os.add_dll_directory on Windows
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_cublas_bin)
    logger.info(f"Added cuBLAS DLL path: {_cublas_bin}")
except ImportError:
    pass

try:
    import nvidia.cudnn
    _cudnn_bin = str(Path(nvidia.cudnn.__path__[0]) / "bin")
    if _cudnn_bin not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _cudnn_bin + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(_cudnn_bin)
    logger.info(f"Added cuDNN DLL path: {_cudnn_bin}")
except ImportError:
    pass

_model = None
_model_loading = False

# Model size: large-v3 for best Korean accuracy on RTX 4090
# Fallback chain: large-v3 → medium → base
MODEL_SIZE = "large-v3"
DEVICE = "cuda"  # Will fallback to cpu if CUDA unavailable
COMPUTE_TYPE = "float16"  # float16 for GPU, int8 for CPU


_actual_device = None  # Track which device was actually used


def get_model():
    """Get or lazily load the Whisper model."""
    global _model, _model_loading, _actual_device

    if _model is not None:
        return _model

    if _model_loading:
        return None

    _model_loading = True
    try:
        from faster_whisper import WhisperModel

        # Try CUDA first, then CPU fallback
        attempts = [
            ("cuda", "float16"),
            ("cuda", "int8_float16"),
            ("cpu", "int8"),
        ]

        for device, compute in attempts:
            try:
                logger.info(f"Loading Whisper '{MODEL_SIZE}' on {device}/{compute}...")
                start = time.time()
                _model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
                _actual_device = device
                # Quick validation: transcribe silence to verify it actually works
                _test_model(_model)
                logger.info(f"Whisper loaded on {device}/{compute} in {time.time() - start:.1f}s")
                return _model
            except Exception as e:
                logger.warning(f"Whisper {device}/{compute} failed: {e}")
                _model = None
                continue

        logger.error("All Whisper load attempts failed")
        _model_loading = False
        return None

    except ImportError:
        logger.error("faster-whisper not installed. Run: pip install faster-whisper")
        _model_loading = False
        return None
    except Exception as e:
        logger.error(f"Failed to load Whisper model: {e}")
        _model_loading = False
        return None


def _test_model(model):
    """Quick smoke test to verify model can actually run inference."""
    import numpy as np
    # Generate 0.5s of silence as float32 audio
    silence = np.zeros(8000, dtype=np.float32)
    segments, info = model.transcribe(silence, language="ko")
    # Consume the generator to trigger actual inference
    for _ in segments:
        pass


async def transcribe_audio(audio_bytes: bytes, language: str = "ko") -> dict:
    """
    Transcribe audio bytes using Whisper.

    Args:
        audio_bytes: Raw audio file bytes (WAV, WebM, MP3, etc.)
        language: Language code (default: Korean)

    Returns:
        {
            "text": str,
            "language": str,
            "duration": float,  # audio duration in seconds
            "processing_time": float,  # transcription time in seconds
            "segments": list,
        }
    """
    import asyncio

    model = get_model()
    if model is None:
        return {
            "text": "",
            "language": language,
            "duration": 0,
            "processing_time": 0,
            "segments": [],
            "error": "Whisper model not available",
        }

    # Write audio to temp file (faster-whisper needs a file path or numpy array)
    try:
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        start_time = time.time()

        # Run transcription in thread pool to avoid blocking event loop
        def _transcribe():
            segments, info = model.transcribe(
                tmp_path,
                language=language,
                beam_size=5,
                vad_filter=True,  # Filter out silence
                vad_parameters=dict(
                    min_silence_duration_ms=300,
                    speech_pad_ms=200,
                ),
            )
            # Materialize segments (generator)
            segment_list = []
            full_text = ""
            for seg in segments:
                segment_list.append({
                    "start": seg.start,
                    "end": seg.end,
                    "text": seg.text.strip(),
                })
                full_text += seg.text

            return full_text.strip(), info.duration, segment_list

        text, duration, segments = await asyncio.get_event_loop().run_in_executor(
            None, _transcribe
        )

        processing_time = time.time() - start_time
        logger.info(
            f"Whisper transcribed {duration:.1f}s audio in {processing_time:.2f}s: "
            f"'{text[:50]}{'...' if len(text) > 50 else ''}'"
        )

        return {
            "text": text,
            "language": language,
            "duration": round(duration, 2),
            "processing_time": round(processing_time, 3),
            "segments": segments,
        }

    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        return {
            "text": "",
            "language": language,
            "duration": 0,
            "processing_time": 0,
            "segments": [],
            "error": str(e),
        }
    finally:
        # Clean up temp file
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


def is_available() -> bool:
    """Check if Whisper is available."""
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def get_status() -> dict:
    """Get Whisper service status."""
    available = is_available()
    model_loaded = _model is not None

    return {
        "available": available,
        "model_loaded": model_loaded,
        "model_size": MODEL_SIZE if available else None,
        "device": _actual_device or DEVICE if available else None,
    }


def preload_model():
    """Pre-load model at startup to avoid first-request delay."""
    import threading
    thread = threading.Thread(target=get_model, daemon=True)
    thread.start()
