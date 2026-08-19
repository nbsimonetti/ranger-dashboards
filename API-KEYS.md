# Optional API keys (Census & BEA)

The dashboards run on free public data. Two **optional** sources need a free API
key. Everything works without them — setting a key just adds extra columns/data.

| Key | Enables | Where it shows up |
|---|---|---|
| `CENSUS_API_KEY` | Census ACS 5-year: **median household income** + **population** | Economic dashboard — county table columns |
| `BEA_API_KEY` | BEA Regional: **per-capita personal income** (table CAINC1) | Economic dashboard — county "PCI (BEA)" column |

The refresh scripts read these from environment variables and skip gracefully when
they are absent (`fetch_acs()` / `fetch_bea()` in `economic/refresh.py`). The
auto-refresh workflow (`.github/workflows/refresh-dashboards.yml`) already passes
them through from repo **secrets** of the same name.

## 1. Get the keys (free, instant)

- **Census:** https://api.census.gov/data/key_signup.html — enter name/email, the
  key arrives by email immediately.
- **BEA:** https://apps.bea.gov/API/signup/ — register, the `UserID` key is emailed.

## 2. Add them as repo secrets

Once you have the keys, run (from the repo, with the `gh` CLI authenticated):

```bash
gh secret set CENSUS_API_KEY --body "YOUR_CENSUS_KEY"
gh secret set BEA_API_KEY    --body "YOUR_BEA_KEY"
```

Or add them in the GitHub UI: **Settings → Secrets and variables → Actions → New
repository secret**.

## 3. Populate

Trigger a refresh so the economic dashboard picks up the new data:

```bash
gh workflow run refresh-dashboards.yml -f only=economic
```

(The weekly scheduled run will also pick them up automatically.) To test locally
instead, export the vars and run the script directly:

```bash
CENSUS_API_KEY=... BEA_API_KEY=... python economic/refresh.py
```
