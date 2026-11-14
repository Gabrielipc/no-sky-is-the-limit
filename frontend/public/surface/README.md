# Surface visualization assets

These are display derivatives, separate from the reviewed scientific results.

- **Mars globe:** NASA MGS/MOLA `MEGR90N000CB`, 4 pixels/degree (about 14.818 km at the equator), final product v2.0. Radius samples are signed big-endian int16 metres with an offset of 3,396,000 m. Unlike areoid-relative topography, this product can displace the declared sphere directly. PDS fills bins without observations by interpolation; this is not a global high-resolution DEM.
- **Tiles:** geographic quadtree, two columns/one row at level zero, levels 0–4, 65 × 65 samples including shared edges. RGB PNG encodes `height = R*256 + G - 32768` metres above the sphere. Blue is unused. East-positive 0–360° input is converted to −180–180°. Bilinear resampling, longitude wrapping, clamped polar rows. Levels are fetched on demand; no additional detail is invented beyond the pyramid.
- **Earth image:** NASA Blue Marble Next Generation, August 2004, downloaded from NASA GIBS as a 2048 × 1024 global image. The Visible Earth/EO Images host was unreachable during preparation. NASA Earth Observatory / Reto Stöckli attribution applies. This is broad context, not local surface imagery.
- **Local meshes:** reprojected from committed, SHA-256-verified HiRISE and SRTM native crops in `docs/evidencia-fase-2`. A local azimuthal equidistant grid spans sample centers from −900 to +900 m. Jezero has 97 × 97 samples at 18.75 m; Earth windows have 61 × 61 samples at 30 m. Output spacing is not a claim about effective sensor resolution.
- **Grayscale PNG:** codes 0–254 map to `offset_m + gray*scale_m`; code 255 is missing. Maximum quantization error is `scale_m/2`. JavaScript decodes data without color conversion, omits faces touching missing samples, and uses median-relative heights in a local east/north/up frame. This local inspection mode hides the globe: its vertical origin is a display datum, not an asserted ellipsoidal height.
- **Local texture:** shaded relief derived from the same DEM, not a satellite photograph. Original absolute elevations are retained in the manifest; the scientific metrics are unchanged.

`manifest.json` records downloaded-source and derivative SHA-256 identities. Original scientific downloads stay in ignored `data/raw/frontend-surface/`.

Reproduction (numpy and rasterio required):

```sh
mkdir -p data/raw/frontend-surface
curl -fL --retry 2 -o data/raw/frontend-surface/megr90n000cb.img 'https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg004/megr90n000cb.img'
curl -fL --retry 2 -o data/raw/frontend-surface/megr90n000cb.lbl 'https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg004/megr90n000cb.lbl'
curl -fL --retry 2 -o data/raw/frontend-surface/blue-marble-gibs.jpg 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.1&LAYERS=BlueMarble_NextGeneration&STYLES=&SRS=EPSG:4326&BBOX=-180,-90,180,90&WIDTH=2048&HEIGHT=1024&FORMAT=image/jpeg'
.venv/bin/python scripts/preparar_superficie_frontend.py
```

Source documentation: [MOLA/PDS](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html), [Blue Marble / Visible Earth](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/), [NASA GIBS](https://nasa-gibs.github.io/gibs-api-docs/access-basics/).
