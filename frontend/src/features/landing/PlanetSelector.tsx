import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Globe2, Moon, Flame, ChevronRight } from 'lucide-react';
import { PLANET_COLORS } from './CinematicJourney';

// ── Configuración de planetas y zonas ──────────────────────
export const PLANETS = [
  {
    id: 'earth' as const,
    label: 'TIERRA',
    sublabel: 'Punto de Origen',
    color: PLANET_COLORS.earth,
    icon: Globe2,
    description: 'Base de operaciones. La geología terrestre como clave para entender el cosmos.',
    analogSite: 'Desierto de Utah, EE.UU.',
    mission: 'El regolito terrestre revela los secretos de otros mundos.',
    zones: null, // Tierra no tiene sub-zonas
  },
  {
    id: 'mars' as const,
    label: 'MARTE',
    sublabel: 'Cráter Jezero',
    color: PLANET_COLORS.mars,
    icon: Flame,
    description: 'El Planeta Rojo aguarda. Rastros de vida antigua en su regolito.',
    analogSite: 'Cráter Jezero — 18.4°N, 77.7°E',
    mission: 'Buscando análogos terrestres para las misiones Perseverance y Artemis.',
    zones: [
      { id: 'jezero-fan',      label: 'Delta Jezero',       sublabel: 'Cráter Jezero' },
      { id: 'olympus-mons',    label: 'Olympus Mons',       sublabel: 'Escudo Volcánico' },
      { id: 'hellas-planitia', label: 'Hellas Planitia',    sublabel: 'Cuenca de Impacto' },
    ],
  },
  {
    id: 'moon' as const,
    label: 'LUNA',
    sublabel: 'Misión Artemis',
    color: PLANET_COLORS.moon,
    icon: Moon,
    description: 'La puerta a las estrellas. Polo Sur lunar: el próximo gran paso.',
    analogSite: 'Polo Sur Lunar — Artemis III',
    mission: 'Encontrar el mejor análogo terrestre para entrenar astronautas.',
    zones: [
      { id: 'shackleton', label: 'Shackleton', sublabel: 'Polo Sur · Artemis' },
      { id: 'haworth',    label: 'Haworth',    sublabel: 'Polo Sur Lunar' },
      { id: 'tycho',      label: 'Tycho',      sublabel: 'Tierra Lunar Sur' },
    ],
  },
] as const;

export type PlanetId = typeof PLANETS[number]['id'];

interface PlanetSelectorProps {
  selected: PlanetId;
  selectedZone: string | null;
  onSelectPlanet: (id: PlanetId) => void;
  onSelectZone: (zone: string) => void;
}

export function PlanetSelector({
  selected,
  selectedZone,
  onSelectPlanet,
  onSelectZone,
}: PlanetSelectorProps) {
  const activePlanet = PLANETS.find(p => p.id === selected)!;

  return (
    <div className="ps-wrapper">
      {/* Tabs de planeta */}
      <div className="ps-tabs" role="tablist" aria-label="Seleccionar planeta">
        {PLANETS.map(planet => {
          const Icon = planet.icon;
          const isActive = selected === planet.id;
          return (
            <button
              key={planet.id}
              role="tab"
              aria-selected={isActive}
              className={`ps-tab ${isActive ? 'ps-tab--active' : ''}`}
              style={isActive ? {
                '--tab-color': planet.color,
                borderColor: planet.color,
                color: planet.color,
                background: `${planet.color}18`,
              } as any : {}}
              onClick={() => onSelectPlanet(planet.id)}
            >
              <Icon size={15} />
              <span>{planet.label}</span>
              {isActive && (
                <motion.div
                  className="ps-tab-indicator"
                  layoutId="tab-indicator"
                  style={{ background: planet.color }}
                />
              )}
            </button>
          );
        })}
      </div>

      {/* Selector de zona (solo para Marte y Luna) */}
      <AnimatePresence mode="wait">
        {activePlanet.zones && (
          <motion.div
            key={selected}
            className="ps-zones"
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
          >
            <div className="ps-zones-label" style={{ color: activePlanet.color }}>
              <ChevronRight size={12} />
              Selecciona una zona para ver el match
            </div>
            <div className="ps-zones-list">
              {activePlanet.zones.map(zone => {
                const isZoneActive = selectedZone === zone.id;
                return (
                  <button
                    key={zone.id}
                    className={`ps-zone-btn ${isZoneActive ? 'ps-zone-btn--active' : ''}`}
                    style={isZoneActive ? {
                      borderColor: activePlanet.color,
                      background: `${activePlanet.color}15`,
                    } : {}}
                    onClick={() => onSelectZone(zone.id)}
                  >
                    <span className="ps-zone-name" style={isZoneActive ? { color: activePlanet.color } : {}}>
                      {zone.label}
                    </span>
                    <span className="ps-zone-sub">{zone.sublabel}</span>
                    {isZoneActive && (
                      <motion.div
                        className="ps-zone-dot"
                        layoutId="zone-dot"
                        style={{ background: activePlanet.color }}
                      />
                    )}
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}


