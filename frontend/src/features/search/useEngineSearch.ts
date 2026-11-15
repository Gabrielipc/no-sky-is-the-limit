import { useEffect, useMemo, useState } from 'react';
import { useSimilaritySearch } from '../../data/similarityApi';
import { buildRequest, type Controls } from '../../domain/similarity';
import { adaptSearch, type LoadedSearch, type ReferenceId } from '../simulation/model';
import { loadSearch } from '../simulation/source';
import { useI18n } from '../../i18n/I18nProvider';

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
  const { t } = useI18n();
  const request = useMemo(() => (controls ? buildRequest(reference, controls) : null), [reference, controls]);
  const live = useSimilaritySearch(request);
  const { loaded, invalid } = useMemo<{ loaded?: LoadedSearch; invalid?: string }>(() => {
    if (!live.data) return {};
    try {
      const data = adaptSearch(live.data);
      if (data.reference.id !== reference) return {};
      return { loaded: {
        data, source: 'live', queryId: live.data.query_id, timings: live.data.timings,
        notice: t('Calculado al momento por el motor de similitud del servidor.', 'Computed on the fly by the server similarity engine.'),
      } };
    } catch (error) { return { invalid: (error as Error).message }; }
  }, [live.data, reference, t]);
  const [demo, setDemo] = useState<{ reference: ReferenceId; value?: LoadedSearch; error?: string }>();
  useEffect(() => {
    if (!live.unavailable) return;
    const controller = new AbortController();
    loadSearch(reference, '', 'demo', `${import.meta.env.BASE_URL}analysis/`, controller.signal)
      .then(value => { if (!controller.signal.aborted) setDemo({ reference, value }); })
      .catch(error => { if (!controller.signal.aborted) setDemo({ reference, error: error.message }); });
    return () => controller.abort();
  }, [live.unavailable, live.error, reference]);
  const fallback = live.unavailable && demo?.reference === reference ? demo : undefined;
  // The notice is composed here so it follows the interface language.
  const demoValue = fallback?.value;
  const demoLoaded = useMemo(() => demoValue && {
    ...demoValue,
    notice: `${live.error} ${t('Se muestra el ejemplo precalculado del repositorio; los parámetros no lo recalculan.', 'Showing the precomputed repository example; the parameters do not recalculate it.')}`,
  }, [demoValue, live.error, t]);
  return {
    loaded: demoLoaded ?? loaded,
    error: fallback ? fallback.error : live.unavailable ? undefined : live.error ?? invalid,
    loading: live.loading || (live.unavailable && !fallback),
    stale: live.stale,
    unavailable: live.unavailable,
    retry: live.retry,
  };
}
export type EngineSearch = ReturnType<typeof useEngineSearch>;
