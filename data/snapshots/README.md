# Frozen registry snapshot

`afijio_public_primary_arcgis.json` is the scoped public registry extract used
by the demonstration: 47 public primary-facility records in Afijio, of which
28 are classified as Primary Health Center. Other subtypes are excluded by
scope, not declared invalid. There are no inventory observations in this file.

Source: [GRID3/NHFR ArcGIS layer](https://services3.arcgis.com/9nfxWATFamVUTTGb/ArcGIS/rest/services/health_facilities_state_WFL1/FeatureServer/1).
Query: `state = 'Oyo' AND lga = 'Afijio' AND ownership = 'Public' AND facility_l = 'Primary'`.
Downloaded for the prototype on 4 October 2026.
SHA-256: `ad04a6afbac0a42736711d2fa6abcf50df8175d55a0033bef5fa02172d3a1c09`.

Docker copies this snapshot rather than downloading changing registry data
during every build. For an intentional source refresh, use
`python -m supplysignal.fetch_sources`, inspect notebook 00, and create a new
release. The broader Oyo download is truncated and is not included here.

## Street basemap

`afijio_basemap.jpg` is a static street map of Afijio stitched from Esri World Street Map tiles at zoom 13 (non-commercial use with attribution: Tiles © Esri, HERE, Garmin, OpenStreetMap contributors). `afijio_basemap.json` holds its Web Mercator tile bounds. Storing it locally lets the app's map work without internet.
