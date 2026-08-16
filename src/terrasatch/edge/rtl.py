"""Receive-only RTL-SDR capture helpers built around the rtl-sdr command line tools."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path


_SUPPORTED_MODES = frozenset({"fm", "am", "wbfm"})


@dataclass(frozen=True, slots=True)
class RtlCaptureConfig:
    frequency_hz: int
    duration_seconds: float = 10.0
    device: str | None = None
    modulation: str = "fm"
    sample_rate_hz: int = 24_000
    output_rate_hz: int = 16_000
    gain_db: float | None = None
    squelch: int | None = None
    ppm: int | None = None

    def validate(self) -> None:
        if self.frequency_hz <= 0:
            raise ValueError("frequency_hz must be greater than zero")
        if not 0.5 <= self.duration_seconds <= 120:
            raise ValueError("duration_seconds must be between 0.5 and 120 seconds")
        if self.modulation not in _SUPPORTED_MODES:
            raise ValueError(f"unsupported modulation: {self.modulation}")
        if not 8_000 <= self.sample_rate_hz <= 3_200_000:
            raise ValueError("sample_rate_hz is outside the supported capture range")
        if not 8_000 <= self.output_rate_hz <= 192_000:
            raise ValueError("output_rate_hz is outside the supported audio range")
        if self.squelch is not None and self.squelch < 0:
            raise ValueError("squelch must be non-negative")
        if self.ppm is not None and not -250 <= self.ppm <= 250:
            raise ValueError("ppm must be between -250 and 250")


def build_rtl_fm_command(config: RtlCaptureConfig, executable: str = "rtl_fm") -> list[str]:
    """Build an argument-vector-only receive command; no shell or transmit utility is used."""

    config.validate()
    command = [
        executable,
        "-M",
        config.modulation,
        "-f",
        str(config.frequency_hz),
        "-s",
        str(config.sample_rate_hz),
        "-r",
        str(config.output_rate_hz),
    ]
    if config.device:
        command.extend(["-d", config.device])
    if config.gain_db is not None:
        command.extend(["-g", str(config.gain_db)])
    if config.squelch is not None:
        command.extend(["-l", str(config.squelch)])
    if config.ppm is not None:
        command.extend(["-p", str(config.ppm)])
    command.append("-")
    return command


def probe_rtl_device(*, device: str | None = None, timeout_seconds: float = 2.0) -> str:
    """Ask rtl_test for receiver startup information and stop it after a short bounded probe."""

    executable = shutil.which("rtl_test")
    if executable is None:
        raise RuntimeError("rtl_test was not found on PATH")
    command = [executable]
    if device:
        command.extend(["-d", device])

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
    output = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    return output or "rtl_test completed without diagnostic output"


def _wait_for_capture(process: subprocess.Popen[bytes], duration_seconds: float) -> bool:
    """Wait for the requested duration and report whether rtl_fm exited unexpectedly early."""

    deadline = time.monotonic() + duration_seconds
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(0.1, remaining))
    return True


def capture_rtl_fm(config: RtlCaptureConfig, output: str | Path) -> Path:
    """Capture bounded demodulated receive audio from rtl_fm into a mono 16-bit WAV file."""

    executable = shutil.which("rtl_fm")
    if executable is None:
        raise RuntimeError("rtl_fm was not found on PATH")
    config.validate()

    destination = Path(output).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            prefix="terrasatch-rtl-",
            suffix=".pcm",
            delete=False,
        ) as raw:
            raw_path = Path(raw.name)
            process = subprocess.Popen(
                build_rtl_fm_command(config, executable=executable),
                stdout=raw,
                stderr=subprocess.PIPE,
            )
            exited_early = _wait_for_capture(process, config.duration_seconds)
            if not exited_early:
                process.terminate()
            try:
                _, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate()

        payload = raw_path.read_bytes()
        detail = stderr.decode("utf-8", errors="replace").strip() if stderr else ""
        if exited_early and process.returncode not in (0, None):
            raise RuntimeError(
                f"rtl_fm exited before the capture duration (code {process.returncode}). {detail}".strip()
            )
        if not payload:
            raise RuntimeError(f"rtl_fm produced no audio samples. {detail}".strip())

        with wave.open(str(destination), "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(config.output_rate_hz)
            recording.writeframes(payload)
        return destination
    finally:
        if raw_path is not None:
            raw_path.unlink(missing_ok=True)
