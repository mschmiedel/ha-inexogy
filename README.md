<img src="custom_components/inexogy/brand/icon.png" alt="" width="96" align="right">

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

### Diagnostic statistics (disabled by default)

A separate **inexogy API** device holds diagnostic sensors about the communication
with the portal. They are disabled by default; enable them on the device page if you
want the numbers (e.g. to tune polling).

| Sensor | Meaning |
| --- | --- |
| API calls | Every HTTP request to the portal (login, refresh, data) |
| Logins / Token refreshes | Full logins and successful refresh-token renewals |
| Polls with / without new data | Whether the latest measurement time of a meter advanced |
| Failed polls | Polls that ended in an error |
| Polls per new value | Successful polls per new measurement (ideal: 1.0) |
| New data ratio | Share of successful polls that brought new data (%) |
| Last API call | Timestamp of the latest request; a recorder/InfluxDB keeps one entry per call |

Counters survive restarts and are deleted together with the integration entry.

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

Enter the **email and password** of your inexogy portal account.
The measurement series is determined automatically (`defaultContainerId` from
`/portal/user/settings`); all meters in it are added as devices.

If the password changes, Home Assistant asks for the new one (re-authentication).

## How it works

- Login: `POST https://api.inexogy.com/portal/auth` with email and password returns
  an access token (about 1 h) and a refresh token (about 3 days). Both are JWTs without
  verifiable signature or issuer, so they are treated as opaque bearer tokens; only the
  (unverified) `exp` claim is read to renew them in time.
- Renewal: `POST /portal/auth/refresh` with `{"token": "<refresh token>"}` returns a new
  pair. If the refresh token is expired or rejected, the integration logs in again with
  email and password. A 401 on a data request triggers one renewal as well.
- Data: `GET /portal/measurement-series/<ID>/recent?from=<ms>&dimension=standard`.
- Value lists are delta-encoded: the first entry carries absolute `time`, `value`
  and `reading`, every following entry only the difference to its predecessor.
- Units: energy in 10⁻¹⁰ kWh, power in mW. Feed-in power is reported negative.

Full details: [`docs/SPEC.md`](docs/SPEC.md). Try the endpoints with your own account
using the [Bruno collection](bruno).

## Contributing

Contributions are welcome – issues and pull requests alike. Please keep these three in
sync with your change, otherwise the pull request cannot be merged:

- [`docs/SPEC.md`](docs/SPEC.md) – specification and architecture (requirement IDs)
- [`bruno/`](bruno) – requests for every portal endpoint the integration uses
- this README (user-visible behaviour, sensors)

`main` is protected: changes go through pull requests with passing checks (HACS, hassfest,
tests). Never include personal data (meter serials, IDs, tokens, addresses) in code,
tests, issues or pull requests. Notes for AI coding agents: [`AGENTS.md`](AGENTS.md).

## Releasing

1. Set `version` in `custom_components/inexogy/manifest.json` (e.g. `1.0.0`) and commit.
2. Push a matching tag: `git tag v1.0.0 && git push origin v1.0.0`.

The release workflow checks that tag and manifest version match and creates the
GitHub release; HACS offers it as an update.

## Icon

The icon ships with the integration in `custom_components/inexogy/brand/`
(`icon.png` 256×256, `icon@2x.png` 512×512); Home Assistant 2026.3 and later
picks it up automatically. The SVG source is `brand/icon.svg`.

## Disclaimer

Not affiliated with or endorsed by inexogy. The portal API is undocumented and may
change at any time.
