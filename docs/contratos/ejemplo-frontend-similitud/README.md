# Ejemplo de vista de similitud (referencia, no integrada)

Implementación de referencia de la búsqueda de análogos sobre el contrato [`similitud-api-v1`](../../../specs/api/similitud-api-v1.schema.json). **No forma parte de la aplicación**: el frontend de este repositorio puede estar desactualizado respecto al vuestro, así que la vista se deja aquí para adaptarla, no se enlaza en el shell.

- `SimilarityWorkspace.tsx`: selector de referencia con sus limitaciones, pesos por vista, resultados con intervalo, mapa y detalle por vista y feature. Solo se acopla con la aplicación por dos props: `referenceId` y `onReferenceChange`.
- `similarity.css`: estilos con los tokens de `frontend/src/styles/tokens.css` (`--surface`, `--line`, `--accent`, `--candidate`, `--muted`).

Para usarla, copiad la carpeta a `frontend/src/features/similarity/`, importad `./similarity.css` y enlazad la vista con vuestro estado. Necesita `data/api.ts` (`useResource`), `data/similarityApi.ts` y `domain/similarity.ts`. Se compiló con `tsc -b` y se probó contra el backend real (debounce de una petición por ráfaga de cambios, sin desbordamiento horizontal a 375 px).
