import { Component, lazy, Suspense, type ReactNode } from "react";
import { loadCesium } from "../../data/loadCesium";
import type { SceneProps } from "./UnifiedScene";
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
        El visor 3D no está disponible. Puedes elegir las ubicaciones en la
        lista y consultar sus medidas.
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
            Cargando Cesium…
          </div>
        }
      >
        <Scene {...props} />
      </Suspense>
    </Boundary>
  );
}
