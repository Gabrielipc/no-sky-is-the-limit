type Position = number[];
type Polygon = Position[][];
/** `name` is Spanish; `name_en` is the English name (Natural Earth NAME_EN). */
export type Country = { name: string; name_en?: string; geometry: { type: 'Polygon'; coordinates: Polygon } | { type: 'MultiPolygon'; coordinates: Polygon[] } };

function inRing(lon: number, lat: number, ring: Position[]): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > lat) !== (yj > lat) && lon < (xj - xi) * (lat - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function countryAt(countries: Country[], latitude: number, longitude: number, lang: 'es' | 'en' = 'es'): string | undefined {
  const country = countries.find(({ geometry }) => {
    const polygons = geometry.type === 'Polygon' ? [geometry.coordinates] : geometry.coordinates;
    return polygons.some(([outer, ...holes]) => outer && inRing(longitude, latitude, outer) && !holes.some(ring => inRing(longitude, latitude, ring)));
  });
  return country && (lang === 'en' ? country.name_en ?? country.name : country.name);
}

