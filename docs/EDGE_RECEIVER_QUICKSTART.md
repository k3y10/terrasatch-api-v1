# TerraListen Edge Receiver Quickstart

TerraListen keeps radio hardware on the local/field computer. `api.terrasatch.com` remains the central multi-tenant backend.

## Modes

### Demo mode

Default mode. No organization, site, or API key is required for local receiver testing.

```bash
terrasatch edge setup
terrasatch edge status
terrasatch edge detect
```

### Connected demo mode

Still uses the simple demo UX. Configure a site once and keep the credential in the environment. The edge client never asks for an organization; the API derives the tenant from the credential.

```bash
terrasatch edge setup --mode demo --site <SITE_UUID>
export TERRASATCH_EDGE_API_KEY='<EDGE_OR_ADMIN_KEY>'
export TERRASATCH_API_BASE_URL='https://api.terrasatch.com'
terrasatch edge api check
```

### Organization mode

Use for a customer/site receiver. The site is stored locally, while the organization remains credential-derived by the API.

```bash
terrasatch edge setup --mode organization --site <SITE_UUID>
export TERRASATCH_EDGE_API_KEY='<EDGE_KEY>'
export TERRASATCH_API_BASE_URL='https://api.terrasatch.com'
terrasatch edge api check
```

The profile is stored under `~/.config/terrasatch/edge.json` by default and never contains the API key.

## WSL: attach the USB receiver

WSL 2 does not receive arbitrary Windows USB devices automatically. Install `usbipd-win` on Windows once.

PowerShell:

```powershell
winget install --interactive --exact dorssel.usbipd-win
```

With WSL open, use an Administrator PowerShell to identify and bind the receiver:

```powershell
usbipd list
usbipd bind --busid <BUSID>
```

Then attach it from PowerShell:

```powershell
usbipd attach --wsl --busid <BUSID>
```

Back in WSL:

```bash
lsusb
```

The Nooelec/NESDR commonly appears as an RTL2832/RTL2838-family USB device.

## Install the RTL-SDR receiver tools on Ubuntu/WSL

```bash
sudo apt update
sudo apt install -y rtl-sdr usbutils
```

Verify TerraListen can see the software and receiver:

```bash
terrasatch edge doctor
terrasatch edge detect
terrasatch edge rtl devices
```

## First Nooelec capture

Use an authorized receive frequency appropriate to the radio/model/region being tested.

```bash
terrasatch edge capture \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10 \
  --output ./bca-test.wav
```

Inspect the resulting WAV:

```bash
terrasatch edge audio inspect ./bca-test.wav
```

Optional receiver tuning:

```bash
terrasatch edge capture \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10 \
  --gain-db <GAIN_DB> \
  --squelch <SQUELCH> \
  --ppm <PPM_CORRECTION> \
  --output ./bca-test.wav
```

Start without manual gain/squelch/PPM and add tuning only when needed.

## On-the-go local demo

No organization or API connection is required:

```bash
terrasatch edge demo \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10
```

This proves the local physical receive path and creates `terrasatch-demo.wav`.

## Connected demo

Until automatic speech-to-text is added, the text is operator-reviewed/provided explicitly:

```bash
terrasatch edge demo \
  --frequency-hz <FREQUENCY_HZ> \
  --seconds 10 \
  --text 'Patrol 4 to base. Wind loading observed on the east aspect.' \
  --callsign 'Patrol 4'
```

If a demo site and API key are configured, the reviewed text is submitted through the existing production transmission pipeline. If they are not configured, the local capture still succeeds and API submission is skipped.

## Receiver compatibility

### RTL-SDR / Nooelec

Current receive-audio backend. TerraListen uses `rtl_test` for a bounded probe and `rtl_fm` for bounded demodulated audio capture.

### HackRF

The receiver registry recognizes HackRF tooling when `hackrf_info` is installed, but this release intentionally does not expose a HackRF audio capture/transmit path. A dedicated receive-only IQ-to-audio adapter can be added behind the same `backend=hackrf` profile later without changing the organization/API model.

## Safety boundary

TerraListen Edge is receive-only. It does not key, PTT, or transmit on the connected radio hardware. Use only radio traffic and frequencies you are authorized to receive/process.

## Architecture

```text
Field radio
   |
   | RF
   v
Nooelec / compatible receiver
   |
   | USB
   v
TerraListen Edge
   |                     local demo: stops here
   |
   | HTTPS (optional)
   v
api.terrasatch.com
   |
   +--> tenant derived from API credential
   +--> configured site
   +--> transmission / transcript / TerraEngine / event
```

References:
- Microsoft WSL USB documentation: https://learn.microsoft.com/windows/wsl/connect-usb
- Nooelec NESDR installation guide: https://support.nooelec.com/hc/en-us/articles/360005298053-NESDR-Installation-Guide
