import { evaluationLabel } from '../domain/analysis';

export function EvidenceStatus({ status }: { status: string }) {
  const evaluated = ['locally_evaluated_exploratory', 'evaluated_exploratory'].includes(status);
  return <span className={`evidence-status ${evaluated ? 'available' : 'pending'}`}><span aria-hidden="true">{evaluated ? '✓' : '◷'}</span> {evaluationLabel(status)}</span>;
}
export function MissingDimensions() {
  return <div className="evidence-strip"><span><b>Medido</b> Inclinación y relieve</span><span><b>Sin evaluar</b> Materiales, térmica, rocas, polvo y agua/hielo</span></div>;
}
export function RequestState({ error, loading, retry }: { error?: string; loading?: boolean; retry: () => void }) {
  if (error) return <div className="request-error" role="alert"><strong>No se pudo cargar esta vista</strong><p>{error}</p><button onClick={retry}>Reintentar</button></div>;
  return loading ? <div className="loading" role="status"><span className="loading-mark" aria-hidden="true" /> Cargando los datos de esta selección…</div> : null;
}
