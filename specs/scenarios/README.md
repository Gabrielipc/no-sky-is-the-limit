# Escenarios

`superficie-multidimensional-v1.json` configura rugosidad residual, posición topográfica y curvatura discreta a 60/120 m para el primer caso, con inercia térmica nativa de Jezero y ausencias explícitas. Se reproduce con `./.pixi/envs/default/bin/python scripts/analizar_dimensiones.py`. Véase [la extensión multidimensional](../../docs/Extension%20multidimensional.md); las comparaciones de materiales, movilidad y térmica Marte–Tierra siguen pendientes.

`estabilidad-topografica-v1.json` configura el segundo escenario: reconocimiento topográfico con sensibilidad a fuente y escala, a partir de ventanas de fase 4. Fija pregunta, referencia, ventana, escalas, margen, selección estratificada determinista y presupuesto. Se ejecuta mediante `./.pixi/envs/default/bin/python scripts/evaluar_expansion.py`; los pendientes de detalle no se puntúan. Ver [entrega de fase 5](../../docs/Fase%205%20-%20expansion%20condicionada.md).

El primer escenario se conserva en `specs/analysis/primer-caso-fase2.json`. Ninguno evalúa movilidad ni incorpora soporte lunar, polar o aprendizaje automático.
