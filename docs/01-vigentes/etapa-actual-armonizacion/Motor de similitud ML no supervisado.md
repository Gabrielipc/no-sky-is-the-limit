# Motor de similitud ML no supervisado

Busca análogos terrestres de una ventana de Marte o la Luna sobre el contrato del Feature Store (`analogos-feature-store-v1`). Compara por varias **vistas** (dimensiones) y deja elegir el peso de cada una en cada consulta.

- Especificación: [`specs/analysis/motor-similitud-ml-v1.json`](../../../specs/analysis/motor-similitud-ml-v1.json)
- Código: [`pipelines/similarity_ml.py`](../../../pipelines/similarity_ml.py), CLI [`scripts/motor_similitud.py`](../../../scripts/motor_similitud.py)
- Tests: [`tests/test_similarity_ml.py`](../../../tests/test_similarity_ml.py)
- Evidencia del primer ajuste: [`docs/evidencia-motor-similitud/`](../../evidencia-motor-similitud/)

## Qué ML usa y por qué

Sigue el veredicto del análisis de viabilidad. No hay etiquetas independientes para entrenar un «score de análogo» supervisado: solo una referencia marciana, dos lunares y unos diez controles terrestres. Por eso el motor aprende **sin etiquetas** la estructura del catálogo terrestre y deja la fusión de vistas en manos de pesos explícitos.

| Componente | Técnica | Qué resuelve |
|---|---|---|
| Transformación por feature | Cuantiles empíricos terrestres → puntuaciones normales | Escalas heterogéneas y colas largas. El percentil terrestre de la referencia queda explícito (Jezero cae en el P76 del relieve). |
| Métrica por vista | Covarianza robusta (Minimum Covariance Determinant con contracción del 5 % a la diagonal) y distancia de Mahalanobis | Colinealidad: los descriptores de escabrosidad (ρ 0,87–0,94 en el ajuste real) no pesan cuatro veces. La distancia se calibra con la CDF χ² de los grados de libertad usados y queda en [0, 1], comparable entre vistas. |
| Regímenes morfológicos | Mezcla gaussiana (GMM, nº de familias por BIC) | Vista `regimen_morfologico`: 1 − coeficiente de Bhattacharyya entre las posteriores de la candidata y de la referencia. |
| Puentes entre cuerpos | Rango intra-cuerpo (espectral, térmica, radar) | Sesgo de instrumento (banda C frente a banda S, EMIT frente a CRISM): nunca se comparan valores crudos. |
| Ausencia estructural | Covarianza marginal por patrón de ausencia y política explícita por vista | Nunca se imputa un valor de feature. Una vista ausente cuenta como neutral (mediana de su distancia en el conjunto), se renormaliza o excluye la candidata, y amplía el intervalo `[score_low, score_high]`. |
| Fusión | Media ponderada (por defecto) o Reciprocal Rank Fusion ponderado | Combina vistas con coberturas distintas. |
| Calibración futura | Bradley-Terry con pesos no negativos sobre pares ciegos | Con los pares del Paso 7, los coeficientes aprendidos son directamente los pesos del contrato. |

**Validación espacial:** la cuenca reservada de Mojave (Leave-One-Basin-Out) queda fuera del ajuste.

## Vistas

`escabrosidad`, `forma_hipsometrica`, `organizacion`, `regimen_morfologico` (topografía directa), `espectral`, `termica` y `radar` (puentes). Los pesos por defecto dependen del cuerpo de la referencia (`default_weights` en el spec). Las vistas no indicadas en `--weight` mantienen su peso por defecto, y un peso 0 apaga la vista.

## Uso

```bash
pixi run python scripts/motor_similitud.py fit
pixi run python scripts/motor_similitud.py search --reference jezero --include-ineligible --limit 10
pixi run python scripts/motor_similitud.py search --reference haworth-fondo --weight escabrosidad=0.6 --weight regimen_morfologico=0.4
pixi run python scripts/motor_similitud.py search --ref-json referencia.json --missing-policy require --fusion rrf
pixi run python scripts/motor_similitud.py calibrate --pairs pares_ciegos.json
```

- **Referencias:** nombradas en el spec (`jezero`, `haworth-fondo`, `de-gerlache-cresta`), cualquier `region_id` del almacén (`--ref-region-id`) o un JSON con `{id, name, body, features, percentiles}`. Las features puente de una referencia sin población suficiente de su cuerpo admiten un percentil intra-cuerpo explícito.
- **Modelo:** se guarda en `data/features/modelos-similitud/` (ignorado por Git) junto a un informe JSON.
- **Salida de cada candidata:** puntuación, intervalo, cobertura y vistas ausentes. Por cada vista incluye la distancia, el percentil en el conjunto y, por feature, el valor crudo, `z_delta` y su `share`. El `share` es la descomposición aditiva exacta de la Mahalanobis² y puede ser negativo o mayor que 1 entre features correlacionadas.

## Estado con el almacén actual (2026-11-14)

- **Ajuste:** 1.453.571 ventanas terrestres rankables fuera de Mojave (muestra de 200.000), en unos 40 s. Cada búsqueda sobre todo el conjunto tarda unos 15 s.
- **Vistas ajustadas:** solo `escabrosidad` (relieve, pendientes P50/P90, rugosidad; 1,14 grados de libertad efectivos) y `regimen_morfologico` (GMM de 8 familias; el BIC seguía bajando en 8, el máximo configurado). Las ventanas terrestres legacy todavía no tienen descriptores de forma ni enriquecimientos espectrales, térmicos o de radar medidos. Esas vistas aparecen como `not_fitted` y quedan fuera de la fusión con un aviso; se activan al reajustar (`fit`) cuando el almacén las tenga.
- **Resultados de ejemplo:** sin compuerta de elegibilidad (`--include-ineligible`), los primeros análogos de Jezero por escabrosidad incluyen ventanas con agua permanente o bosque denso. Esto confirma que la forma hipsométrica y la elegibilidad deben entrar antes de interpretar un ranking. Con la compuerta por defecto solo hay 8 ventanas elegibles hoy.
- **Estado del motor:** `unsupervised_pending_blind_validation`. Los pesos son un prior declarado hasta calibrarlos con la revisión ciega.
