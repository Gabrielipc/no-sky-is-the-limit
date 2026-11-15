import { useEffect, useRef, useState } from 'react';
import { Cartesian3, Color, Ellipsoid, Globe, ImageryLayer, SingleTileImageryProvider, Viewer } from 'cesium';
import 'cesium/Build/Cesium/Widgets/widgets.css';

import type { Location } from './domain/analysis';

export function ContextGlobe({ site }: { site: Location }) {
  const windowKm = (site.window_m / 1000).toLocaleString('es');
  const container = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    if (!container.current) return;
    setError('');
    const mars = site.body === 'Mars';
    const radius = site.radius_m ?? 3394839.8133163;
    const ellipsoid = mars ? new Ellipsoid(radius, radius, radius) : Ellipsoid.WGS84;
    let viewer: Viewer;
    try {
      viewer = new Viewer(container.current, { ellipsoid, globe: new Globe(ellipsoid), baseLayer: false,
        baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
        navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false,
        infoBox: false, selectionIndicator: false });
      viewerRef.current = viewer;
      viewer.scene.globe.baseColor = Color.fromCssColorString(mars ? '#8d4936' : '#315c67');
      SingleTileImageryProvider.fromUrl(
        mars ? `${import.meta.env.BASE_URL}surface/mars-globe.png` : `${import.meta.env.BASE_URL}surface/blue-marble.png`,
        { ellipsoid },
      )
        .then(provider => { if (!viewer.isDestroyed()) viewer.imageryLayers.add(new ImageryLayer(provider)); })
        .catch(() => { if (!viewer.isDestroyed()) setError('No se pudo cargar la textura global; se muestra un fondo uniforme.'); });
      viewer.entities.add({ position: Cartesian3.fromDegrees(site.longitude, site.latitude, 0, ellipsoid),
        point: { pixelSize: 9, color: Color.fromCssColorString('#c5e59e'), outlineColor: Color.BLACK, outlineWidth: 2 } });
      viewer.entities.add({ polyline: { width: 3, material: Color.WHITE,
        positions: site.area.geometry.coordinates[0].map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat, 30, ellipsoid)) } });
      viewer.camera.setView({ destination: Cartesian3.fromDegrees(site.longitude, site.latitude, (mars ? radius : 6378137) * 1.5, ellipsoid) });
    } catch {
      if (viewerRef.current && !viewerRef.current.isDestroyed()) viewerRef.current.destroy();
      viewerRef.current = null;
      setError('No se pudo iniciar el globo. Las coordenadas y geometrías siguen disponibles en la evidencia.');
    }
    return () => { viewerRef.current = null; if (viewer && !viewer.isDestroyed()) viewer.destroy(); };
  }, [site.id, site.window_m]);
  function move(local: boolean) {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const ellipsoid = viewer.scene.globe.ellipsoid;
    viewer.camera.flyTo({ destination: Cartesian3.fromDegrees(site.longitude, site.latitude,
      local ? site.window_m * 2 : ellipsoid.maximumRadius * 1.5, ellipsoid), duration: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 1 });
  }
  return <><div className="globe-wrap"><div className="globe" ref={container} aria-label={`Ubicación contextual de ${site.name}`} />
    <div className="globe-tools"><button onClick={() => move(false)}>Vista global</button><button onClick={() => move(true)}>Ver polígono de {windowKm} km</button></div></div>
    <p className="muted small">{site.body === 'Mars' ? 'Fondo MOLA en colores falsos · NASA Mars Trek.' : 'Fondo Blue Marble · NASA/Goddard SVS.'} Contorno de la ventana analizada. La textura es contexto regional; el globo no muestra terreno 3D ni el detalle del análisis.</p>
    {error && <p role="alert" className="error small">{error}</p>}</>;
}
