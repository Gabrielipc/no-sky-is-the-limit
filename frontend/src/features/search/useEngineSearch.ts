import { useEffect, useMemo, useState } from 'react';
import { useSimilaritySearch } from '../../data/similarityApi';
import { buildRequest, type Controls } from '../../domain/similarity';
import { adaptSearch, type LoadedSearch, type ReferenceId } from '../simulation/model';
import { loadSearch } from '../simulation/source';

/** Controls of the public mode: the server's own weights and the first ten matches. */
export const SIMPLE_CONTROLS: Controls = {
  weights: {}, touched: false, onlyEligible: true, fusion: 'weighted', missingPolicy: 'neutral', limit: 10,
};

/**
 * Live search through `POST /api/similarity/search` (both modes). Only when the server has no engine
 * (503 or no connection) does it fall back to the repository example, flagged as such: it is never
 * presented as a live answer.
 */
export function useEngineSearch(reference: ReferenceId, controls: Controls | null) {
  const request = useMemo(() => (controls ? buildRequest(reference, controls) : null), [reference, controls]);
  const live = useSimilaritySearch(request);
  const { loaded, invalid } = useMemo<{ loaded?: LoadedSearch; invalid?: string }>(() => {
    if (!live.data) return {};
    try {
      const data = adaptSearch(live.data);
      if (data.reference.id !== reference) return {};
      return { loaded: {
        data, source: 'live', queryId: live.data.query_id, timings: live.data.timings,
        notice: 'Calculado al momento por el motor de similitud del servidor.',
      } };
    } catch (error) { return { invalid: (error as Error).message }; }
  }, [live.data, reference]);
  const [demo, setDemo] = useState<{ reference: ReferenceId; value?: LoadedSearch; error?: string }>();
  useEffect(() => {
    if (!live.unavailable) return;
    const controller = new AbortController();
    loadSearch(reference, '', 'demo', `${import.meta.env.BASE_URL}analysis/`, controller.signal)
      .then(value => { if (!controller.signal.aborted) setDemo({ reference, value: { ...value, notice: `${live.error} Se muestra el ejemplo precalculado del repositorio; los parámetros no lo recalculan.` } }); })
      .catch(error => { if (!controller.signal.aborted) setDemo({ reference, error: error.message }); });
    return () => controller.abort();
  }, [live.unavailable, live.error, reference]);
  const fallback = live.unavailable && demo?.reference === reference ? demo : undefined;
  return {
    loaded: fallback?.value ?? loaded,
    error: fallback ? fallback.error : live.unavailable ? undefined : live.error ?? invalid,
    loading: live.loading || (live.unavailable && !fallback),
    stale: live.stale,
    unavailable: live.unavailable,
    retry: live.retry,
  };
}
export type EngineSearch = ReturnType<typeof useEngineSearch>;
