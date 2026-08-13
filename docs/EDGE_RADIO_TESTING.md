# TerraSatch receive-only edge radio testing

This guide validates a local Nooelec/RTL-SDR receiver and the production TerraSatch ingest pipeline without adding any radio transmit or PTT behavior.

## Architecture boundary

Run the receiver commands on the computer physically connected to the Nooelec device. Do not attach the SDR to the Oracle API server.

```text
BCA / authorized test radio
        |
        | RF transmission
        v
Nooelec RTL-SDR receiver (local field computer)
        |
        | rtl_fm receive + demodulated PCM
        v
TerraSatch edge WAV capture
        |
        | operator review / current text bridge
        v
POST https://api.terrasatch.com/api/v1/transmissions
        |
        v
Transmission -> Transcript -> TerraEngine -> OperationalEvent -> REST / WebSocket
```

TerraSatch edge commands in this release are receive-only. They do not key, program, control, or transmit through a BCA radio.

## Receiver prerequisites

Nooelec documents its NESDR family as RTL-SDR compatible. Install the correct device driver/setup for the operating system first. The TerraSatch CLI expects the rtl-sdr command-line utilities `rtl_test` and `rtl_fm` to be available on `PATH`.

Primary references:

- Nooelec NESDR installation guide: https://support.nooelec.com/hc/en-us/articles/360005298053-NESDR-Installation-Guide
- Nooelec supported SDR software: https://support.nooelec.com/hc/en-us/articles/360005243074-Supported-SDR-Software
- Osmocom rtl-sdr project: https://github.com/osmocom/rtl-sdr
- BCA BC Link radio resources and model-specific frequency charts: https://backcountryaccess.com/en-us/support/bc-link-radio-resources

The BCA frequency must come from the frequency chart for the exact radio/region being tested. Do not guess a frequency from a channel number.

## 1. Check the local edge machine

```bash
terrasatch edge doctor
```

Expected for RTL capture:

```text
[OK] rtl_test: ...
[OK] rtl_fm: ...
Receive-only boundary: no TerraSatch edge command keys or transmits a radio.
```

## 2. Probe the Nooelec receiver

Connect the Nooelec device to the local machine, then run:

```bash
terrasatch edge rtl devices
```

The command runs a short bounded `rtl_test` probe and then stops it. If the operating system has claimed the device as a DVB adapter or the current user lacks USB permission, resolve the driver/udev setup before continuing.

## 3. Capture a short radio test

Choose a legal/authorized test channel on the BCA radio and look up its receive frequency in the appropriate BCA frequency chart. Supply the frequency in Hz.

Terminal A:

```bash
terrasatch edge rtl capture \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10 \
  --output ./bca-test.wav
```

While the capture is running, make a short authorized test transmission on the BCA radio. A useful test phrase is:

```text
Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.
```

Do not use emergency channels, operational channels you are not authorized to use, or transmit solely for testing where radio rules prohibit it.

## 4. Inspect the captured audio

```bash
terrasatch edge audio inspect ./bca-test.wav
```

The report includes duration, sample rate, PCM width, RMS, peak, and whether the file contains non-zero audio energy. This is a capture diagnostic, not a speech-quality score.

## 5. Configure API access on the edge machine

Issue a TerraSatch API key for the intended organization with the `edge:ingest` scope (an `admin` key also has the scope override). Keep the raw key only on the edge machine.

```bash
export TERRASATCH_API_BASE_URL=https://api.terrasatch.com
export TERRASATCH_EDGE_API_KEY='<raw edge key>'
```

Do not pass the API key as a command-line flag or commit it to a repository.

Verify the credential:

```bash
terrasatch edge api check
```

The output should identify the organization and report `edge:ingest: ready` without printing the key.

## 6. Prove the production intelligence pipeline

Until automatic STT is added, submit the operator-reviewed text heard in the capture:

```bash
terrasatch edge submit-text \
  --site <SITE_UUID> \
  --callsign 'Patrol 4' \
  --text 'Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.'
```

Expected result:

- a Transmission is persisted with source `edge-rtl`;
- a Transcript is persisted;
- TerraEngine extracts an OperationalEvent;
- the event is available from `/api/v1/events` and the tenant WebSocket stream.

You can also bind the operator-reviewed text to the same capture invocation:

```bash
terrasatch edge rtl capture \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10 \
  --output ./bca-test.wav \
  --site <SITE_UUID> \
  --callsign 'Patrol 4' \
  --submit-text 'Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.'
```

`--submit-text` is explicitly a human-reviewed bridge. It does not claim that speech recognition has occurred.

## Acceptance checklist

- [ ] `terrasatch edge doctor` finds `rtl_test` and `rtl_fm`.
- [ ] `terrasatch edge rtl devices` identifies/opens the Nooelec receiver.
- [ ] A short BCA test produces a WAV file.
- [ ] `edge audio inspect` reports non-zero audio energy.
- [ ] `edge api check` authenticates and reports `edge:ingest: ready`.
- [ ] `edge submit-text` creates a transmission and at least one event.
- [ ] The resulting event is visible through the REST API.
- [ ] The receiver workflow contains no transmit/PTT operation.

## Next hardware layer

After this boundary is proven on the actual receiver, add local speech segmentation and STT so the WAV/audio stream can automatically produce the transcript passed to `/api/v1/transmissions`. Keep the same edge API boundary so the Oracle backend and partner applications do not need to change when the speech provider changes.
