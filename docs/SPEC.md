# inexogy integration – specification & architecture

This document is the single source of truth for what the integration does and how it
is built. It combines the functional specification and the architecture description.
Requirements carry stable IDs (`REQ-…`, `NFR-…`, `ADR-…`) so that code, tests,
issues and pull requests can reference them.

**Rule:** behaviour changes start here. Update the affected requirement (or add a new
one) in the same pull request as the code, and keep [`bruno/`](../bruno) and the
[README](../README.md) in sync.

---

## 1. Purpose and scope

Show the smart meter data of an [inexogy](https://inexogy.com) account (grid import and
export, meter readings, power) in Home Assistant, using the same undocumented API as
the inexogy web portal.

**In scope:** reading current values, one HA device per meter, Energy dashboard support,
diagnostics about the API usage.

**Out of scope:** writing anything to inexogy, tariffs/costs, market prices, the
documented public API with OAuth1 (used by the Home Assistant core integration).

## 2. Glossary

| Term | Meaning |
| --- | --- |
| Account | inexogy portal login (email + password). Can hold several containers. |
| Measurement series / container | Portal object with a 32-hex-char ID (`defaultContainerId`, `containers[].id`). Usually exactly one meter (`meterSerialNumbers`); interval, last measurement and offline state exist per container, not per meter. All data endpoints work per container. One HA config entry per container. |
| Meter | Physical smart meter, identified by its serial number. A bidirectional meter has two registers: import (`CONSUMPTION`, OBIS 1.8.0) and export (`FEED`, OBIS 2.8.0). |
| Serial variants | The same meter appears as `1ABC0012345678` (with manufacturer prefix) and `12345678`. |
| Measurement interval | Raster of the measurements, 15 min (`measurementInterval` = 900000 ms). |
| Measurement time | Quarter-hour timestamp a value belongs to (not the time it was delivered). |
| Delivery delay | Time between measurement time and availability in the API; observed 6–21 min, irregular at night. |
| Poll | One call to the `recent` endpoint by the coordinator. |

## 3. External interface: inexogy portal API

Base URL `https://api.inexogy.com/portal`. All requests except auth use
`Authorization: Bearer <accessToken>`. Executable examples: [`bruno/`](../bruno).

| Endpoint | Used | Purpose |
| --- | --- | --- |
| `POST /auth` `{"email","password"}` | yes | Login → `accessToken` (~1 h), `refreshToken` (~3 d) |
| `POST /auth/refresh` `{"token": <refreshToken>}` | yes | New `accessToken` (also as `token`) and `refreshToken` |
| `GET /user/settings` | yes (config flow) | `defaultContainerId` |
| `GET /measurement-series/{id}/recent?from=<ms>&dimension=standard` | yes (every poll) | Current readings and recent 15-min power intervals |
| `GET /containers?pageNo=0&pageSize=30` | yes (config flow with meter number) | All containers incl. `measurementInterval`, `meterSerialNumbers`, `offline`; paged, `totalCount` |
| `GET /measurement-series/{id}/consumption?from&to&frequency=daily…` | planned | Historic values per day |

### 3.1 Token semantics

- JWTs without verifiable signature or issuer. They are opaque bearer tokens; only the
  unverified `exp` claim is read to renew them in time. Not OAuth2.
- Login rejection: HTTP 400/401/403.

### 3.2 Response format (`recent`, `consumption`)

A JSON list; each element is one series:

| Field | Meaning |
| --- | --- |
| `meterSerialNumber` | Serial, in one of its variants |
| `type` | `ENERGY` (meter reading) or `POWER` (interval average) |
| `seriesType` | `CONSUMPTION` (grid import) or `FEED` (grid export) |
| `values[]` | `time` (ms), `value`, `reading` – **delta-encoded**: first entry absolute, every following entry the difference to its predecessor |

Units: energy `value`/`reading` in 10⁻¹⁰ kWh, power `value` in mW. Feed-in power is
negative. In `recent`, `ENERGY` has one entry (current reading), `POWER` one entry per
15-min interval of the requested window.

## 4. Functional requirements

### Setup and authentication

- **REQ-01** The config flow asks for email, password and an optional meter number.
  Empty: the container is `defaultContainerId`. Set: the container whose
  `meterSerialNumbers` contains the number (exact match first, else a unique match with
  or without manufacturer prefix, at least 8 characters; case, spaces and dashes
  ignored). Only email, password
  and the container ID are stored. Errors: `invalid_auth`, `cannot_connect`,
  `meter_not_found`, `no_series_id`, `no_data`.
- **REQ-02** One config entry per measurement series (unique ID = series ID). The entry
  title is the account email. Titles of older versions (`inexogy <id prefix>`,
  `inexogy <serial(s)>`) are migrated; user-defined titles stay untouched.
- **REQ-03** Tokens: renew the access token shortly (60 s) before `exp` via
  `/auth/refresh`; if the refresh token is expired or rejected, log in again. A 401/403 on
  a data request discards the access token and retries once.
- **REQ-04** Rejected credentials start Home Assistant's re-authentication flow
  (password only).

### Data and entities

- **REQ-10** Poll `recent` every 5 minutes with a look-back of 3 hours.
- **REQ-11** Series are grouped per meter; serial variants that are suffixes of a longer
  serial belong to that meter, named after the longest variant. Series without serial
  belong to the only meter, else to `unknown`.
- **REQ-12** One device per meter, named `inexogy <serial>`. Meters appearing later are
  added on the next update; a meter missing from a response becomes unavailable.
- **REQ-13** Sensors per meter:

  | Key | Unit | State class | Source |
  | --- | --- | --- | --- |
  | `consumption_energy` | kWh | total_increasing | latest ENERGY/CONSUMPTION value |
  | `feed_in_energy` | kWh | total_increasing | latest ENERGY/FEED value |
  | `consumption_power` | W | measurement | \|latest POWER/CONSUMPTION\| |
  | `feed_in_power` | W | measurement | \|latest POWER/FEED\| |
  | `net_power` | W | measurement | consumption − feed-in |
  | `last_measurement` | timestamp | – | latest POWER measurement time |

- **REQ-14** Unique IDs: meter sensors `<series>_<serial>_<key>`, device
  `(inexogy, <series>_<serial>)`. Pre-0.4.0 IDs (`<series>_<key>`, device `<series>`) are
  migrated to the first meter so entity IDs and history are kept.

### Diagnostics

- **REQ-20** The device of the container's first meter carries diagnostic sensors
  (API calls are per container; usually it is the only meter), all **disabled by
  default**, always available (they also count failures):
  `api_calls`, `logins`, `token_refreshes`, `polls_new_data`, `polls_no_new_data`,
  `polls_failed` (total_increasing), `polls_per_new_value`, `new_data_ratio` (%),
  `last_api_call` (timestamp). Unique IDs `<series>_api_<key>`.
- **REQ-21** A poll has *new data* if the latest measurement time of at least one meter is
  later than the one seen before. `polls_per_new_value` = successful polls / polls with
  new data; `new_data_ratio` = polls with new data / successful polls.
- **REQ-22** Counters and last seen measurement times are stored in HA storage
  (`inexogy.<entry_id>.stats`), saved with 60 s delay, immediately on unload, and deleted
  when the entry is removed.
- **REQ-23** 1.1.0rc1 put the diagnostics on a separate service device
  `(inexogy, <series>_api)`. On setup its entities are moved to the meter device (entity
  IDs, enabled state and history kept) and the old device is removed.

## 5. Non-functional requirements

- **NFR-01 API load.** Many installations multiply every call. Avoid calls that cannot
  return anything new; prefer fewer, well-timed polls (see §8).
- **NFR-02 Privacy.** No personal data in the repository: no real serials, series IDs,
  tokens, emails, names, addresses. Tests and docs use synthetic values.
- **NFR-03 Compatibility.** Home Assistant ≥ 2025.2 (`hacs.json`); brand icon from
  `custom_components/inexogy/brand/` needs ≥ 2026.3. Python 3.13.
- **NFR-04 Languages.** English (`strings.json`, `translations/en.json`) and German
  (`translations/de.json`) are always complete and in sync.
- **NFR-05 Robustness.** Unknown fields and missing series must not crash parsing; failed
  polls leave entities unavailable (meter sensors) without losing statistics.

## 6. Architecture

### 6.1 Building blocks

```
custom_components/inexogy/
├── __init__.py      setup/unload/remove, migrations (REQ-02, REQ-14)
├── config_flow.py   user + reauth flow (REQ-01, REQ-04)
├── coordinator.py   DataUpdateCoordinator: polling, poll statistics, storage (REQ-10, REQ-21/22)
├── api.py           InexogyClient: HTTP, tokens, call counters (REQ-03, REQ-20)
├── parser.py        pure: delta decoding, units, grouping per meter (REQ-11, REQ-13)
├── stats.py         pure: ApiStats counters and ratios (REQ-20/21)
├── sensor.py        meter sensors and diagnostic sensors (REQ-12/13, REQ-20)
├── const.py         constants, ID helpers
├── strings.json, translations/   UI texts (NFR-04)
└── brand/           icon (NFR-03)
```

`parser.py` and `stats.py` have no Home Assistant imports and are unit tested directly.

### 6.2 Runtime view

**Setup:** create client → coordinator loads stored statistics → first refresh (login,
`recent`) → migrate device/entity IDs and title → forward to sensor platform.

**Poll (every 5 min):** ensure token (valid / refresh / login) → `GET recent` → parse →
compare measurement times (new data or not) → update counters, schedule save → entities
update from the coordinator.

### 6.3 Decisions

- **ADR-01** Tokens are opaque; only `exp` is decoded unverified. No OAuth2 library.
- **ADR-02** Use the portal API (email/password) instead of the public OAuth1 API, which
  did not work for the author's account.
- **ADR-03** Group by longest serial variant (REQ-11) instead of trusting
  `meterSerialNumber` literally – otherwise one meter becomes two devices.
- **ADR-04** Device/entity IDs include series and serial; migrations keep history (REQ-14).
- **ADR-05** Brand icon ships inside the integration; home-assistant/brands no longer
  accepts custom integrations.
- **ADR-06** Statistics are entity counters plus HA storage, not a database; long-term
  analysis happens in the recorder/InfluxDB.

## 7. Quality and delivery

- CI (`.github/workflows/validate.yml`): HACS validation (no ignores), hassfest, ruff,
  pytest. Required checks on protected `main`; changes only via pull request.
- Releases: bump `version` in `manifest.json`, merge, push tag `v<version>`;
  `release.yml` checks tag = manifest version and creates the GitHub release.
  Tags `vX.Y.Z` become releases; `vX.Y.Z(a|b|rc)N` become pre-releases, which HACS
  offers only to users with beta versions enabled. Other tag formats fail.
- Versioning: semantic, pre-releases in PEP 440 style (`1.1.0rc1` < `1.1.0`). New
  entities/behaviour → minor, fixes → patch.

## 8. Roadmap (not implemented)

- **Adaptive polling.** First poll at measurement time + interval + X, retries after 5,
  10, 15 min up to the next interval; X learned per installation: per day, if the share
  of polls without new data is high, X += 30 s, if it is low, X −= 30 s, bounded.
  Exponential backoff on errors/429. Interval from `containers.measurementInterval`.
  Goal (NFR-01): ~50–67 % fewer calls with the same freshness.
- **Containers.** Use `measurementInterval` as polling raster and add an `offline`
  sensor (both per container).
- **External statistics.** Import hourly sums with their real timestamps for the Energy
  dashboard (fills gaps, correct hour attribution).
