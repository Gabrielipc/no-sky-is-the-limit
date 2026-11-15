import { Component, lazy, Suspense, type ReactNode } from "react";
import { loadCesium } from "../../data/loadCesium";
import type { SceneProps } from "./UnifiedScene";
import { tr } from "../../i18n/lang";
const Scene = lazy(async () => {
  await loadCesium();
  return import("./UnifiedScene");
});
class Boundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  render() {
    return this.state.error ? (
      <p role="alert" className="u-missing">
        {tr(
          "El visor 3D no está disponible. Puedes elegir las ubicaciones en la lista y consultar sus medidas.",
          "The 3D viewer is not available. You can still pick locations from the list and check their measurements.",
        )}
      </p>
    ) : (
      this.props.children
    );
  }
}
export function ScenePanel(props: SceneProps) {
  return (
    <Boundary>
      <Suspense
        fallback={
          <div className="u-scene" role="status">
            {tr("Cargando Cesium…", "Loading Cesium…")}
          </div>
        }
      >
        <Scene {...props} />
      </Suspense>
    </Boundary>
  );
}
