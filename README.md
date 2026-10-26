# inexogy for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz/)
[![Validate](https://github.com/mschmiedel/ha-inexogy/actions/workflows/validate.yml/badge.svg)](https://github.com/mschmiedel/ha-inexogy/actions/workflows/validate.yml)

Unofficial Home Assistant integration for smart meters read out by
[inexogy](https://inexogy.com). It uses the same API as the inexogy web portal.

## Sensors

One device per meter found in the measurement series, named `inexogy <meter serial>`.
Meters that appear later are added automatically.

| Sensor | Unit | Notes |
| --- | --- | --- |
| Grid consumption | kWh | Meter reading (import), `total_increasing` – usable in the Energy dashboard |
| Grid feed-in | kWh | Meter reading (export), `total_increasing` – usable in the Energy dashboard |
| Grid consumption power | W | Average import power of the latest 15-minute interval |
| Grid feed-in power | W | Average export power of the latest 15-minute interval |
| Net grid power | W | Import minus export (negative while exporting) |
| Last measurement | timestamp | End of the latest interval delivered by the portal |

The portal is polled every 5 minutes. Values arrive with the delay of the
inexogy backend (typically 15 minutes or more), so this is not a real-time source.

## Installation

### HACS

1. HACS → ⋮ → *Custom repositories* → add `https://github.com/mschmiedel/ha-inexogy`, category *Integration*.
2. Install **inexogy** and restart Home Assistant.

### Manual

Copy `custom_components/inexogy` into your `config/custom_components` folder and restart Home Assistant.

## Configuration

*Settings → Devices & services → Add integration → inexogy*

- **Email / password** of your inexogy portal account
- **Measurement series ID** (optional): leave it empty to use the account's default
  meter (`defaultContainerId` from `/portal/user/settings`). Only needed for accounts
  with several meters: it is the 32-character hex string in requests to
  `…/portal/measurement-series/<ID>/…` (browser developer tools, network tab).

If the password changes, Home Assistant asks for the new one (re-authentication).

## How it works

- Login: `POST https://api.inexogy.com/portal/auth` with email and password returns
  an access token. The token is a JWT without verifiable signature or issuer, so it is
  treated as an opaque bearer token. The integration logs in again shortly before the
  token's (unverified) `exp` claim or whenever the API answers with 401.
- Data: `GET /portal/measurement-series/<ID>/recent?from=<ms>&dimension=standard`.
- Value lists are delta-encoded: the first entry carries absolute `time`, `value`
  and `reading`, every following entry only the difference to its predecessor.
- Units: energy in 10⁻¹⁰ kWh, power in mW. Feed-in power is reported negative.

## Disclaimer

Not affiliated with or endorsed by inexogy. The portal API is undocumented and may
change at any time.
