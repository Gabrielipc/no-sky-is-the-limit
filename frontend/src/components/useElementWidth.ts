import { useEffect, useRef, useState } from 'react';
/** Keep SVG labels at readable screen-pixel sizes instead of shrinking a fixed viewBox. */
export function useElementWidth(defaultWidth = 450) {
  const ref = useRef<SVGSVGElement>(null);
  const [width, setWidth] = useState(defaultWidth);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(220, Math.round(entry.contentRect.width))));
    observer.observe(node); return () => observer.disconnect();
  }, []);
  return { ref, width };
}
