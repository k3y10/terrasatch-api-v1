# TerraSatch Receive-Side Hardware Testing

This guide validates the first physical receive path without adding radio transmission control to TerraSatch.

## Boundary

TerraSatch edge tooling is receive-only. It does not key PTT, program a radio, bypass radio controls, or make autonomous life-safety decisions. Use a frequency/channel that you are authorized to use and follow the documentation and rules for the specific radio model and location.

The first hardware acceptance milestone is intentionally:

```text
BCA radio (manual TX by operator)
  -> Nooelec / RTL-SDR receive
  -> rtl_fm demodulated PCM
  -> WAV capture
  -> operator confirms audio
  -> manual transcript submission
  -> POST /api/v1/transmissions
  -> Transcript
  -> TerraEngine
  -> OperationalEvent
  -> PostgreSQL / Redis / REST / WebSocket
```

Automatic VAD and speech-to-text are **not** claimed by this milestone. They are the next edge increment after RF/audio capture is proven.

## 1. Prepare the edge workstation

Use the computer physically connected to the Nooelec receiver. Do not plug the USB receiver into the Oracle API server.

Install the rtl-sdr command-line utilities for your operating system so these commands are on `PATH`:

```text
rtl_test
rtl_fm
```

Nooelec documents the NESDR family as RTL2832U-based receivers. The upstream rtl-sdr project provides both the device-test and FM-demodulation utilities used by this edge layer.

References:

- https://support.nooelec.com/hc/en-us/articles/360005805834-NESDR-Series
- https://github.com/osmocom/rtl-sdr
- https://backcountryaccess.com/en-us/support/downloads

## 2. Configure outbound API access

Issue a TerraSatch API key for the test organization with at least:

```text
edge:ingest
read:transmissions
read:transcripts
read:events
```

On the edge workstation, keep the credential in the environment rather than the command line:

```bash
export TERRASATCH_API_BASE_URL=https://api.terrasatch.com
export TERRASATCH_EDGE_API_KEY='<secret-api-key>'
```

Never commit the key.

## 3. Run diagnostics

```bash
terrasatch edge doctor --check-api
terrasatch edge devices
```

`edge doctor` verifies tool discovery and public API readiness without opening the SDR. `edge devices` opens the receiver briefly with a bounded `rtl_test` probe.

## 4. Determine the authorized receive frequency

Use the manual/frequency chart for the exact BCA BC Link model and the channel you are authorized to test. BCA publishes BC Link radio frequency charts and model-specific manuals from its support downloads page.

TerraSatch deliberately does not hard-code a BCA frequency because radio model, channel plan, privacy-code configuration, and regional requirements can differ.

Convert the selected receive frequency to integer Hz for the CLI. Example format only:

```text
155.000 MHz -> 155000000 Hz
```

The example is a formatting example, not a recommended BCA channel.

## 5. Dry-run the receive command

```bash
terrasatch edge capture-rtl \
  --frequency-hz <AUTHORIZED_FREQUENCY_HZ> \
  --seconds 8 \
  --output terrasatch-rx.wav \
  --dry-run
```

This prints the exact argv that would be passed to `rtl_fm` and does not open the device.

## 6. Capture a BCA test transmission

Place the BCA radio and receive antenna a reasonable distance apart so the SDR front end is not unnecessarily overloaded. Key the BCA radio manually and speak a short, unambiguous test phrase during the capture window.

Suggested phrase:

```text
Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.
```

Start the receiver:

```bash
terrasatch edge capture-rtl \
  --frequency-hz <AUTHORIZED_FREQUENCY_HZ> \
  --seconds 10 \
  --output terrasatch-bca-test.wav
```

Inspect the generated file:

```bash
terrasatch edge inspect-wav terrasatch-bca-test.wav
```

Play it with any normal WAV player and confirm the spoken phrase is intelligible.

## 7. Prove the existing API pipeline

Until automatic STT is connected, submit what was actually spoken as the manual transcript:

```bash
terrasatch edge submit-text \
  --site <SITE_UUID> \
  --callsign 'Patrol 4' \
  --text 'Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.' \
  --json
```

The response should contain the persisted transmission, transcript, and TerraEngine event(s).

For a single combined acceptance command:

```bash
terrasatch edge acceptance \
  --frequency-hz <AUTHORIZED_FREQUENCY_HZ> \
  --site <SITE_UUID> \
  --callsign 'Patrol 4' \
  --text 'Patrol 4 to base. Wind loading observed on the east aspect around 9800 feet.' \
  --seconds 10 \
  --output terrasatch-bca-test.wav \
  --json
```

The command explicitly reports:

```text
rf_audio_captured: true
automatic_stt_validated: false
manual_transcript_submitted: true
```

## 8. Verify persisted intelligence

Use the API or Swagger UI with a credential that has the matching read scopes:

```text
GET /api/v1/transmissions
GET /api/v1/transcripts
GET /api/v1/events
```

For the suggested test phrase, TerraEngine should preserve the callsign and source provenance and recognize the east aspect and approximately 9800-foot elevation.

## Next hardware milestone

After this acceptance flow passes reliably:

1. add voice activity detection / squelch-aware segmentation;
2. add a local speech-to-text provider adapter;
3. feed recognized text into the existing transmission service automatically;
4. add confidence/latency metadata;
5. run repeated BCA-to-Nooelec end-to-end tests;
6. only then consider a supervised long-running edge-agent service with store-and-forward behavior.
