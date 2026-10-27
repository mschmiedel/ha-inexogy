# Bruno collection

Requests for every inexogy portal endpoint the integration uses (or plans to use),
for support and for checking the API with your own account in
[Bruno](https://www.usebruno.com/).

| Request | Used by the integration |
| --- | --- |
| 01 Login | yes |
| 02 Refresh token | yes |
| 03 User settings | yes (config flow) |
| 04 Containers | yes (config flow, when a meter number is entered) |
| 05 Recent values | yes (every poll) |
| 06 Consumption daily | planned |

## Usage (app)

1. Open this folder as a collection in Bruno and select the environment `inexogy`.
2. In the environment settings, enter `email` and `password`. Both are *secret*
   variables: Bruno stores their values locally only, never in these files.
3. Run `01 Login`, then `03 User settings` (fills `seriesId`), then any other request.
   Tokens and IDs live in runtime variables; nothing is written back to the files.

## Usage (CLI)

```bash
bru run --env inexogy --env-var email=you@example.com --env-var password='...'
```

With 1Password, without the password ever touching your shell history:

```bash
bru run --env inexogy --env-var email="$(op read 'op://Private/inexogy/username')" --env-var password="$(op read 'op://Private/inexogy/password')"
```

## Privacy

Responses contain personal data (name, address, meter serials, IDs, tokens).
Redact them before sharing anything in issues or pull requests.
