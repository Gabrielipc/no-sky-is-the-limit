/**
 * English versions of the Spanish texts stored in the Nicaragua precomputation
 * (`analysis/nicaragua/analogos-nicaragua-v1.json`). They are keyed by the exact Spanish text, so a
 * regenerated file with new wording falls back to its Spanish original instead of showing a stale
 * translation.
 */
import type { Lang } from './model';

const EN: Record<string, string> = {
  // Known sites
  'Marte temprano': 'early Mars',
  'GVP (Smithsonian), centro del volcán': 'GVP (Smithsonian), volcano centre',
  'Aproximadas (Atlas Obscura); campo geotérmico al pie del Telica':
    'Approximate (Atlas Obscura); geothermal field at the foot of Telica',
  'Alteración ácido-sulfática de basalto en fumarolas: sulfatos (yeso, natroalunita), sílice, hematita esferoidal y goethita, filosilicatos.':
    'Acid-sulfate alteration of basalt at fumaroles: sulfates (gypsum, natroalunite), silica, spherical hematite and goethite, phyllosilicates.',
  'Basalto joven de química parecida a la marciana alterado por gases sulfurosos; la hematita asociada a natroalunita sugiere una vía de formación para depósitos de hematita en Marte.':
    'Young basalt with a Mars-like chemistry altered by sulfurous gases; hematite associated with natroalunite suggests a formation pathway for hematite deposits on Mars.',
  'Sistema hidrotermal ácido activo: azufre, sílice, yeso y sulfatos hidratados según la temperatura y la acidez de cada fumarola.':
    'Active acid hydrothermal system: sulfur, silica, gypsum and hydrated sulfates depending on the temperature and acidity of each fumarole.',
  'Uno de los tres volcanes activos del estudio de alteración ácido-sulfática como análogo de sistemas hidrotermales fósiles de Marte.':
    'One of the three active volcanoes in the acid-sulfate alteration study, as an analogue of fossil hydrothermal systems on Mars.',
  'Fumarolas ácidas con sulfatos, sílice y filosilicatos.': 'Acidic fumaroles with sulfates, silica and phyllosilicates.',
  'Incluido en el mismo estudio de alteración ácido-sulfática junto con Cerro Negro y Momotombo.':
    'Included in the same acid-sulfate alteration study as Cerro Negro and Momotombo.',
  'Ollas de lodo hirviente y fumarolas de baja temperatura: sulfatos hidratados y filosilicatos.':
    'Boiling mud pots and low-temperature fumaroles: hydrated sulfates and phyllosilicates.',
  'Campo de lodos hidrotermales estudiado como análogo de alteración ácido-sulfática más fría y menos ácida.':
    'Hydrothermal mud field studied as an analogue of cooler, less acidic acid-sulfate alteration.',
  'Hervideros de San Jacinto': 'San Jacinto mud pots',
  // Citations written (partly) in Spanish
  'Hynek, B. M., McCollom, T. M., Marcucci, E. C., Brugman, K. y Rogers, K. L. (2013). Assessment of environmental controls on acid-sulfate alteration at active volcanoes in Nicaragua: Applications to relic hydrothermal systems on Mars. Journal of Geophysical Research: Planets, 118(10), 2083-2104.':
    'Hynek, B. M., McCollom, T. M., Marcucci, E. C., Brugman, K. and Rogers, K. L. (2013). Assessment of environmental controls on acid-sulfate alteration at active volcanoes in Nicaragua: Applications to relic hydrothermal systems on Mars. Journal of Geophysical Research: Planets, 118(10), 2083-2104.',
  'Hynek, B. M. et al. (2007). Resumen sobre Cerro Negro (Nicaragua) como análogo terrestre de la meteorización ácido-sulfática de basaltos parecidos a los de Marte. GSA Annual Meeting, Denver, trabajo 129449.':
    'Hynek, B. M. et al. (2007). Abstract on Cerro Negro (Nicaragua) as a terrestrial analogue for acid-sulfate weathering of Mars-like basalts. GSA Annual Meeting, Denver, paper 129449.',
  'NASA Exobiology: Cerro Negro, Nicaragua: an analog for assessing the potential for life on early Mars (proyecto 282, archivo 2008).':
    'NASA Exobiology: Cerro Negro, Nicaragua: an analog for assessing the potential for life on early Mars (project 282, 2008 archive).',
  // Method notes
  'El motor compara la forma del relieve (escabrosidad, forma hipsométrica, organización de las pendientes y régimen morfológico). Las vistas espectral y térmica aún no están ajustadas para la Tierra, así que la mineralogía no entra en la distancia.':
    'The engine compares the shape of the relief (ruggedness, hypsometric shape, slope organisation and morphological regime). The spectral and thermal views are not yet fitted for Earth, so mineralogy does not enter the distance.',
  'No se aplica el filtro de superficie árida: casi todo Nicaragua tiene bosque, cultivos o agua. La cobertura de cada ventana se muestra aparte y no cambia la distancia; con más de un 5 % de árboles la rugosidad no se mide y esa feature queda ausente.':
    'The arid-surface filter is not applied: almost all of Nicaragua has forest, crops or water. The land cover of each window is shown separately and does not change the distance; with more than 5% tree cover roughness is not measured and that feature is left missing.',
  'Zona volcánica: centro de ventana a 10 km o menos de un volcán holoceno del GVP. Ahí se añadieron ventanas cada 2 km con el mismo extractor del atlas global (Copernicus GLO-30 a 30 m); fuera, solo hay una ventana cada 10 km.':
    'Volcanic zone: window centre within 10 km of a GVP Holocene volcano. There, windows were added every 2 km with the same extractor as the global atlas (Copernicus GLO-30 at 30 m); elsewhere there is only one window every 10 km.',
  'Las ventanas con al menos un 50% de agua permanente (lagos y lagunas) no se clasifican.':
    'Windows with at least 50% permanent water (lakes and lagoons) are not ranked.',
  'Los análogos conocidos lo son por la literatura (mineralogía y procesos hidrotermales); el motor solo indica si su relieve también se parece a la referencia.':
    'Known analogues come from the literature (mineralogy and hydrothermal processes); the engine only tells whether their relief also resembles the reference.',
  'Distancia menor = más parecido. El puesto mundial compara con todas las ventanas terrestres clasificables del atlas, no solo con Nicaragua.':
    'Lower distance = more similar. The world rank compares with every rankable Earth window in the atlas, not only with Nicaragua.',
  // Sources and boundary
  'Natural Earth 1:10m Admin 0 – Countries (dominio público)': 'Natural Earth 1:10m Admin 0 – Countries (public domain)',
  'Contorno de referencia para recortar ventanas; no es un límite oficial. Incluye el Lago Cocibolca y el de Managua dentro del polígono.':
    'Reference outline used to clip windows; it is not an official boundary. Lake Cocibolca and Lake Managua are inside the polygon.',
  'Global Volcanism Program, Smithsonian Institution · Volcanoes of the World (volcanes holocenos)':
    'Global Volcanism Program, Smithsonian Institution · Volcanoes of the World (Holocene volcanoes)',
};

/** A Spanish text from the precomputation, in the interface language when a translation exists. */
export const dataText = (text: string, lang: Lang): string => (lang === 'en' ? EN[text] ?? text : text);
