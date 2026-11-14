import type { ReactNode } from 'react';
export function MethodDrawer({ title = 'Fuentes y método', children }: { title?: string; children: ReactNode }) {
  return <details className="method-drawer"><summary>{title}</summary><div className="drawer-content">{children}</div></details>;
}
export function EvidenceLinks({ links }: { links: Record<string, string> }) {
  return <div className="evidence-links">{Object.entries(links).map(([name, url]) => <a key={name} href={url} target="_blank" rel="noreferrer">{name} ↗</a>)}</div>;
}
