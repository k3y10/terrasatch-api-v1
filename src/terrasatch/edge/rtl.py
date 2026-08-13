"""Receive-only RTL-SDR discovery and bounded audio capture helpers."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path


class RTLToolUnavailable(RuntimeError):
    """Raised when the local rtl-sdr command-line tools are unavailable."""


class RTLCaptureError(RuntimeError):
    """Raised when an RTL-SDR capture cannot produce usable receive audio."""


@dataclass(frozen=True, slots=True)
class RTLReceiveConfig:
    """Validated receive-only parameters passed to ``rtl_fm``."""

    frequency_hz: int
    sample_rate: int = 24_000
    output_rate: int = 24_000
    device: str = "0"
    gain_db: float | None = None
    squelch: int = 0
    modulation: str = "fm"

    def __post_init__(self) -> None:
        if self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be positive")
        if not 8_000 <= self.sample_rate <= 300_000:
            raise ValueError("sample_rate must be between 8000 and 300000 Hz")
        if not 8_000 <= self.output_rate <= 96_000:
            raise ValueError("output_rate must be between 8000 and 96000 Hz")
        if not self.device.strip():
            raise ValueError("device cannot be blank")
        if not 0 <= self.squelch <= 100:
            raise ValueError("squelch must be between 0 and 100")
        if self.modulation not in {"fm", "am", "usb", "lsb"}:
            raise ValueError("modulation must be one of fm, am, usb, or lsb")


def find_rtl_tools() -> dict[str, str | None]:
    """Return local rtl-sdr executable paths without mutating the host."""

    return {"rtl_test": shutil.which("rtl_test"), "rtl_fm": shutil.which("rtl_fm")}


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RTLToolUnavailable(
            f"{name} was not found on PATH. Install the rtl-sdr command-line tools on the edge host."
        )
    return path


def build_rtl_fm_command(config: RTLReceiveConfig) -> list[str]:
    """Build an argv-only, receive-side ``rtl_fm`` command."""

    command = [
        require_tool("rtl_fm"),
        "-f",
        str(config.frequency_hz),
        "-M",
        config.modulation,
        "-s",
        str(config.sample_rate),
        "-r",
        str(config.output_rate),
        "-d",
        config.device,
        "-l",
        str(config.squelch),
    ]
    if config.gain_db is not None:
        command.extend(["-g", f"{config.gain_db:g}"])
    command.append("-")
    return command


def probe_rtl_device(*, device: str = "0", timeout_seconds: float = 2.0) -> tuple[bool, str]:
    """Probe one RTL device with a bounded ``rtl_test`` receive attempt.

    ``rtl_test`` normally keeps reading until interrupted. Reaching the timeout after the tool has
    opened the receiver is therefore treated as a successful probe; immediate device/library errors
    are returned as failures.
    """

    rtl_test = require_tool("rtl_test")
    command = [rtl_test, "-d", device]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        output = _timeout_output(error)
        if _looks_like_device_failure(output):
            return False, output.strip() or "RTL-SDR probe failed"
        return True, output.strip() or "RTL-SDR opened and receive probe remained active"

    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    if result.returncode == 0 and not _looks_like_device_failure(output):
        return True, output or "RTL-SDR probe completed"
    return False, output or f"rtl_test exited with status {result.returncode}"


def capture_rtl_wav(
    config: RTLReceiveConfig,
    *,
    seconds: float,
    output_path: Path,
) -> dict[str, object]:
    """Capture a bounded receive-only ``rtl_fm`` session to mono signed-16-bit WAV."""

    if not 0.25 <= seconds <= 120:
        raise ValueError("seconds must be between 0.25 and 120")

    command = build_rtl_fm_command(config)
    output_path = output_path.expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(prefix="terrasatch-rtl-", suffix=".pcm") as raw_file:
        process = subprocess.Popen(
            command,
            stdout=raw_file,
            stderr=subprocess.PIPE,
            text=False,
        )
        started = time.monotonic()
        try:
            time.sleep(seconds)
        finally:
            process.terminate()
            try:
                _, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate(timeout=2)

        elapsed = max(time.monotonic() - started, 0.0)
        raw_file.flush()
        raw_file.seek(0)
        pcm = raw_file.read()

    stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""
    if not pcm:
        raise RTLCaptureError(stderr_text.strip() or "rtl_fm produced no receive audio")

    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(config.output_rate)
        wav.writeframes(pcm)

    return {
        "output": str(output_path),
        "frequency_hz": config.frequency_hz,
        "sample_rate": config.output_rate,
        "seconds_requested": seconds,
        "seconds_elapsed": round(elapsed, 3),
        "bytes_pcm": len(pcm),
        "device": config.device,
        "modulation": config.modulation,
        "stderr": stderr_text.strip(),
    }


def _timeout_output(error: subprocess.TimeoutExpired) -> str:
    stdout = error.stdout.decode(errors="replace") if isinstance(error.stdout, bytes) else error.stdout
    stderr = error.stderr.decode(errors="replace") if isinstance(error.stderr, bytes) else error.stderr
    return "\n".join(part for part in (stdout, stderr) if part)


def _looks_like_device_failure(output: str) -> bool:
    lowered = output.casefold()
    markers = (
        "no supported devices found",
        "failed to open rtlsdr device",
        "usb_open error",
        "libusb_error_access",
        "permission denied",
    )
    return any(marker in lowered for marker in markers)
