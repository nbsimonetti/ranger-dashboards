# CRE Environmental Screening: data sources

Probe log for every source the dashboard uses. Endpoints were checked on 18 November 2026. Every source below answered a scripted request from this machine. The "browser" column records whether the service returns an `Access-Control-Allow-Origin` header for the GitHub Pages origin, which decides whether the page can query it live.

## Built into the county shards (`refresh.py`)

| Source | Endpoint | Format | Browser | Texas records | Refresh |
|---|---|---|---|---|---|
| EPA Facility Registry Service, Texas combined state file | `ordsext.epa.gov/FLA/www3/state_files/state_combined_tx.zip` | ZIP of CSVs (about 100 MB) | n/a (built) | NPL 56 (+14 deleted), SEMS 417 active and 924 archived, RCRA TSD 179, RCRA generators about 12,000, ACRES brownfields 1,167, TRI 5,637, formal enforcement 7,053, industrial stormwater permits 23,747 | Weekly |
| TCEQ remediation layers (Superfund, LPST, VCP, Brownfields, IHW corrective action, Innocent Owner/Operator, Dry Cleaner Remediation, Municipal Setting Designations, landfills) | `gisweb.tceq.texas.gov/arcgis/rest/services/Public/<layer>/MapServer/0` | ArcGIS REST JSON, 1,000 per page | Yes | Superfund 168, LPST 29,866, VCP 3,265, Brownfields 213, IHWCA 5,748, IOP 1,335, DCRP 389, MSD 550, active landfills 193 | Weekly |
| TCEQ Petroleum Storage Tanks | `.../Public/PST/MapServer/0` | ArcGIS REST JSON | Yes | 18,774 facilities with active-tank counts | Weekly |
| TCEQ LPST case list (reported and closure dates) | Texas Open Data Portal `data.texas.gov/resource/hedz-nn4q` | Socrata JSON | n/a (built) | 29,874 cases, about 1,070 open | Weekly; joined to the LPST points by LPST id |
| TCEQ operating and historical dry cleaner registrations | `data.texas.gov/resource/qfph-9bnd`, `xcc6-2a52` | Socrata JSON, address only | n/a (built) | 3,711 registrations, 3,331 geocoded | Weekly; new addresses geocoded with the US Census batch geocoder and cached in `data/cache/drycleaner-geocodes.json` |
| Railroad Commission orphan, injection/disposal and commercial disposal wells; Operator Cleanup, Voluntary Cleanup and Brownfield Response sites; commercial waste disposal facilities | `gis.rrc.texas.gov/server/rest/services/rrc_public/RRC_Public_Viewer_Srvs/MapServer/<2,3,4,33,34,35,36>` | ArcGIS REST JSON | Yes | Orphan 12,234, injection/disposal 46,935, commercial disposal 1,897, OCP 3,432, VCP 186, Brownfield 42, commercial waste 88 | Weekly |
| CRE parcels | `cre/cre-dashboard-tx.html` (`var ALL`) and `cre/cre-coords-tx.json` | Embedded JSON | n/a (built) | 161,859 parcels; 100,304 with a geocode inside their own county. 8,419 geocodes fell in a different county (parcel ids repeat across counties and the coordinate file is keyed by id alone) and were dropped; 53,136 parcels have no geocode | Only with `--parcels`; sub-types come from the CRE page's own `getSubtype()` run under node |
| SBA 7(a) and 504 loans at the parcel address | `loan-maturity/loans_statewide.json` | JSON | n/a (built) | 1,671 parcels matched by normalized street address within the county | With `--parcels` |

## Queried live from the page

| Source | Endpoint | Browser | Use |
|---|---|---|---|
| FEMA National Flood Hazard Layer | `hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28` (zones), `/3` (FIRM panels) | Yes | Zone at the point, Special Flood Hazard Area within 250 ft, panel and effective date |
| US Fish and Wildlife Service National Wetlands Inventory | `fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer/0` | Yes | Wetland at the point and within 500 ft |
| Railroad Commission well locations (1.4 million) | `.../RRC_Public_Viewer_Srvs/MapServer/1` | Yes | Wells within 1/4 mile, by type |
| Railroad Commission pipelines | `.../RRC_Public_Viewer_Srvs/MapServer/13` | Yes | Segments within 500 ft, operator and commodity |

## Rules sources

- Ranger Bank Credit Policy, Section 8.3 Environmental Risk Management: the Phase I triggers and heightened-diligence collateral.
- SBA SOP 50 10 8.1 (effective 1 October 2026), the environmental investigation steps and Appendix 6 (environmentally sensitive NAICS codes) and Appendix 7 (gas stations). The official sba.gov link redirected to `legacy.sba.gov`, which did not resolve from this network on 18 November 2026, so the text was taken from a published copy of the SOP and checked for the Appendix 6 list and the $250,000 questionnaire threshold. Re-check against sba.gov when it is reachable.
- ASTM E1527-21 minimum search distances, Table 1, by list class.

## Not used, and why

- **Census one-line geocoder in the browser.** It sends no CORS header, so typed street addresses cannot be geocoded from the page. The batch geocoder is used offline for dry cleaner addresses.
- **EPA EJScreen.** EPA took it offline in 2025.
- **CARTO basemap tiles.** They now return "API key required" tiles. The page uses OpenStreetMap tiles.
- **Federal RCRA corrective action (CORRACTS).** It is not in the FRS state file. Texas runs corrective action under its RCRA authorization, so the TCEQ IHW corrective action layer covers it.
- **Closed landfills.** TCEQ publishes active landfills only on its public layer.
- **EPA radon zones.** No machine-readable county table was found from an authoritative source.

## Records left out

- EPA FRS facilities in the selected programs with no coordinates (3,312) cannot be placed on the map.
- Points that fall outside every Texas county polygon are dropped (about 360 on a full build: EPA and TCEQ records whose coordinates fall outside Texas).
- Dry cleaner registrations whose address did not match in the Census geocoder (380).

## Failure handling

Each source runs inside its own try/except. A source that fails keeps its records from the previous shards, is marked `stale` in `data/index.json` with the error, and shows as stale in the page's freshness ribbon. The script still exits 0, so the weekly CI job carries on. On 18 November 2026 the EPA download reset mid-transfer once; the run kept 27,394 EPA records and flagged EPA stale, as designed. `--frs-zip <path>` builds from a downloaded copy of the EPA file when the download keeps failing.
