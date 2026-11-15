# Derivados visuales del visor unificado

Generados con `frontend/scripts/prepare-unified-terrain.py`. Solo se versionan
imágenes de navegador y metadatos, nunca los originales científicos de `data/raw/`.
`catalog.json` identifica cada ubicación, centro, datum, fuente, cobertura, rango,
escala del gris, error de cuantización y SHA-256. Gris 255 = sin dato, nunca cero.

- Luna global: NASA CGI Moon Kit (https://svs.gsfc.nasa.gov/4720/), LOLA float TIFF
  de 4 píxeles/grado. Alturas originales en km convertidas a metros respecto a la
  esfera de 1.737.400 m; longitud centrada en 0°, norte arriba. Pirámide RGB
  (R × 256 + G − 32768 m), niveles 0–3, 65 vértices por lado. El incremento de
  detalle termina en la fuente real (~7,6 km en el ecuador). La imagen LROC de 2025
  incluye relleno polar de albedo LOLA: es contexto visual, no fotometría analítica.
- Haworth y De Gerlache: LOLA ajustado 2009–2022, 20 m por píxel, marco MOON_ME_DE421,
  https://pgda.gsfc.nasa.gov/products/90. Lectura HTTP acotada del COG polar; se
  reproyectan ventanas azimutales equidistantes centradas en las coordenadas del
  catálogo `specs/sources/luna-polar-sur-v1.json`. La resolución efectiva depende
  de la densidad de trazas. Coordenadas de Haworth aproximadas; De Gerlache tiene
  precisión publicada de dos decimales (~300 m), no representa un emplazamiento exacto.
- Tierra: Copernicus DEM GLO-30 público, COGs de
  https://copernicus-dem-30m.s3.amazonaws.com. Resolución nativa 1 segundo de arco,
  DSM relativo a EGM2008. Lecturas acotadas por ventana; una sola tesela por centro,
  por lo que bordes externos sin soporte se conservan como huecos. Incluye objetos
  superficiales, agua o vegetación; no cambia la elegibilidad original de la ventana.
- Jezero: recorte HiRISE ya disponible en `surface/manifest.json`, remuestreado
  de 18,75 m a la rejilla visual común de 30 m. El primer PNG ya estaba cuantizado;
  el error original se añade al error de la segunda cuantización, no se recupera
  precisión con el remuestreo.

Ventana local: 61 × 61 vértices, 30 m entre vértices, 1,8 km entre extremos.
Ventana regional lunar/terrestre: 161 × 161 vértices, 150 m, 24 km entre extremos.
El remuestreo bilineal sirve a la visualización, no a una nueva medición del motor.
La geometría regional usa posiciones sobre el cuerpo curvo (geodésica esférica);
las mallas locales usan un marco este/norte/arriba y altura relativa a su mediana.
Los rangos de color son compartidos entre los dos DEM locales válidos. Los datums
absolutos de los cuerpos son distintos y no se restan entre sí.

Las demostraciones del ranking usan ventanas de 3 km, pendiente con base 240 m y
rugosidad con radio 360 m. La pendiente visual usa diferencias centrales de 60 m
en la rejilla de 30 m; no sustituye ese descriptor. No se genera rugosidad ficticia.
Ni zoom, ni exageración, ni capa cambian las mediciones publicadas.

Jezero regional: MOLA 128 ppd, rango ya verificado del proyecto
MEGR44N000HB.IMG (filas 3072–3455, bytes 70778880–79626239),
SHA-256 430ae7fb3b811bbe48697856d9ed21a412a1d14b4b29181cf7df474628bc762f.
Muestreo nativo ~463 m, remuestreado a 150 m para el visor; esta interpolación no
aporta detalle nuevo. El recorte CTX se proyecta sobre la malla con coordenadas
por vértice de su rectángulo geográfico original, sin estirar la imagen al recorte.
