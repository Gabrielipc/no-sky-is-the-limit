import { useEffect, useRef, useState } from "react";
import {
  ArcGisMapServerImageryProvider,
  ArcGISTiledElevationTerrainProvider,
  BoundingSphere,
  Cartesian2,
  Cartesian3,
  Cartographic,
  Color,
  ComponentDatatype,
  CustomDataSource,
  CustomHeightmapTerrainProvider,
  Ellipsoid,
  EllipsoidGeometry,
  EllipsoidalOccluder,
  EllipsoidGeodesic,
  EllipsoidTerrainProvider,
  Entity,
  GeographicProjection,
  GeographicTilingScheme,
  Geometry,
  GeometryAttribute,
  GeometryAttributes,
  GeometryInstance,
  GeometryPipeline,
  Globe,
  HeadingPitchRange,
  ImageryLayer,
  Material,
  MaterialAppearance,
  Math as CMath,
  Matrix4,
  Primitive,
  PrimitiveType,
  Rectangle,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  SingleTileImageryProvider,
  Transforms,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { asset, pixels } from "../surface/assets";
import {
  decodeMola,
  elevationColor,
  meshArrays,
  metricScale,
  type SurfaceManifest,
  type SurfaceMode,
} from "../surface/terrain";
import { localGuides } from "../surface/guides";
import {
  offsetDegrees,
  groupMapPoints,
  visualValues,
  type Grid,
  type VisualLayer,
} from "./terrainModel";
export type Mark = {
  id: string;
  name: string;
  longitude: number;
  latitude: number;
};
export type SceneProps = {
  body: "Mars" | "Moon" | "Earth";
  name: string;
  longitude: number;
  latitude: number;
  marks: Mark[];
  selected: string;
  choose: (id: string) => void;
  mode: SurfaceMode;
  grid?: Grid;
  layer: VisualLayer;
  range: [number, number];
  exaggeration: number;
  overview?: boolean;
  missing?: string;
  pending?: boolean;
};
const queuedDraws = new WeakSet<Viewer>();
/** Commit prop/camera changes immediately, even when Safari throttles background frames. */
function draw(viewer: Viewer) {
  viewer.scene.requestRender();
  if (queuedDraws.has(viewer)) return;
  queuedDraws.add(viewer);
  queueMicrotask(() => {
    queuedDraws.delete(viewer);
    if (viewer.isDestroyed()) return;
    viewer.resize();
    viewer.render();
    queueMicrotask(() => {
      if (!viewer.isDestroyed()) viewer.render();
    });
  });
}
const colors = { Mars: "#E2694A", Moon: "#E8DAC2", Earth: "#72AED6" };
export default function UnifiedScene(p: SceneProps) {
  const root = useRef<HTMLDivElement>(null),
    view = useRef<Viewer>(),
    props = useRef(p);
  props.current = p;
  const wakeUntil = useRef(performance.now() + 4000);
  const [mapButtons, setMapButtons] = useState<
    { id: string; name: string; x: number; y: number; members: string[] }[]
  >([]);
  const [contextOnly, setContextOnly] = useState(true);
  const [ready, setReady] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState("Cargando contexto…"),
    [frame, setFrame] = useState(0),
    [scale, setScale] = useState<ReturnType<typeof metricScale>>(null),
    [heading, setHeading] = useState(0);
  const terrainMesh = useRef<Primitive>(),
    guides = useRef<CustomDataSource>(),
    details = useRef<ImageryLayer>();
  useEffect(() => {
    if (!root.current) return;
    const c = new AbortController();
    let v: Viewer | undefined,
      handler: ScreenSpaceEventHandler | undefined,
      disposed = false,
      removeCamera: (() => void) | undefined,
      removeRender: (() => void) | undefined;
    setReady(false);
    setError("");
    setStatus("Cargando contexto…");
    const radius =
      p.body === "Mars" ? 3396000 : p.body === "Moon" ? 1737400 : 6378137;
    const ellipsoid =
      p.body === "Earth"
        ? Ellipsoid.WGS84
        : new Ellipsoid(radius, radius, radius);
    try {
      v = new Viewer(root.current, {
        ellipsoid,
        globe: new Globe(ellipsoid),
        mapProjection: new GeographicProjection(ellipsoid),
        terrainProvider: new EllipsoidTerrainProvider({ ellipsoid }),
        baseLayer: false,
        baseLayerPicker: false,
        geocoder: false,
        homeButton: false,
        sceneModePicker: false,
        navigationHelpButton: false,
        animation: false,
        timeline: false,
        fullscreenButton: false,
        infoBox: false,
        selectionIndicator: false,
        useDefaultRenderLoop: false,
        requestRenderMode: false,
        targetFrameRate: 30,
        maximumRenderTimeChange: Infinity,
        scene3DOnly: true,
        skyAtmosphere: false,
      });
      view.current = v;
      v.useBrowserRecommendedResolution = false;
      v.resolutionScale =
        Math.min(devicePixelRatio || 1, 1.5) / (devicePixelRatio || 1);
      v.scene.backgroundColor = Color.fromCssColorString("#1C1511");
      v.scene.globe.baseColor = Color.fromCssColorString(colors[p.body]);
      v.scene.globe.enableLighting = false;
      v.scene.globe.maximumScreenSpaceError = 3;
      v.scene.globe.tileCacheSize = 70;
      if (v.scene.skyBox) v.scene.skyBox.show = false;
      v.scene.screenSpaceCameraController.minimumZoomDistance = 40;
      v.scene.screenSpaceCameraController.maximumZoomDistance = radius * 6;
      const texture =
        p.body === "Mars"
          ? `${import.meta.env.BASE_URL}textures/mars.png`
          : asset(
              p.body === "Moon" ? "unified/moon-color.jpg" : "blue-marble.png",
            );
      // Keep a georeferenced context body visible while terrain workers prepare
      // root tiles. This has no elevation and is removed once the globe is ready.
      const contextBody = v.scene.primitives.add(
        new Primitive({
          geometryInstances: new GeometryInstance({
            geometry: new EllipsoidGeometry({
              radii: ellipsoid.radii,
              stackPartitions: 64,
              slicePartitions: 128,
              vertexFormat:
                MaterialAppearance.MaterialSupport.TEXTURED.vertexFormat,
            }),
          }),
          appearance: new MaterialAppearance({
            material: new Material({
              fabric: {
                type: "RegolithGlobalContext",
                uniforms: { image: texture },
                source:
                  "czm_material czm_getMaterial(czm_materialInput materialInput) { czm_material m=czm_getDefaultMaterial(materialInput); vec4 c=texture(image,vec2(fract(materialInput.st.s+0.5),materialInput.st.t)); m.diffuse=c.rgb; m.alpha=c.a; return m; }",
              },
            }),
            translucent: false,
            closed: true,
          }),
          asynchronous: false,
        }),
      );
      SingleTileImageryProvider.fromUrl(texture, {
        ellipsoid,
        credit:
          p.body === "Moon"
            ? "NASA CGI Moon Kit · LROC + LOLA"
            : p.body === "Mars"
              ? "NASA MOLA · color de elevación"
              : "NASA Blue Marble",
      })
        .then((provider) => {
          if (!disposed && v) {
            v.imageryLayers.add(new ImageryLayer(provider), 0);
            wakeUntil.current = performance.now() + 4000;
            draw(v);
          }
        })
        .catch(() => {
          if (!disposed)
            setError(
              "Imagen global ausente. Se mantienen las coordenadas y el relieve válido.",
            );
        });
      const install = (provider: Viewer["terrainProvider"], label: string) => {
        if (disposed || !v || v.isDestroyed()) return;
        v.terrainProvider = provider;
        wakeUntil.current = performance.now() + 4000;
        provider.errorEvent.addEventListener(() => {
          if (!disposed)
            setStatus(
              "Relieve incompleto · contexto sin detalle en teselas ausentes",
            );
        });
        setStatus(label);
        draw(v);
      };
      if (p.body === "Earth")
        ArcGISTiledElevationTerrainProvider.fromUrl(
          "https://elevation3d.arcgis.com/arcgis/rest/services/WorldElevation3D/Terrain3D/ImageServer",
        )
          .then((provider) =>
            install(provider, "Esri World Elevation · streaming"),
          )
          .catch(() => {
            if (!disposed)
              setStatus("Relieve global sin servicio · elipsoide de contexto");
          });
      else
        fetch(asset("manifest.json"), { signal: c.signal })
          .then((r) => {
            if (!r.ok) throw Error();
            return r.json() as Promise<SurfaceManifest>;
          })
          .then((m) => {
            if (disposed || !v) return;
            const moon = p.body === "Moon",
              size = 65,
              max = moon ? 3 : (m.mola.regional?.max_level ?? m.mola.max_level),
              base = moon ? 3 : m.mola.max_level,
              available = new Set(m.mola.regional?.tiles || []);
            const provider = new CustomHeightmapTerrainProvider({
              width: size,
              height: size,
              tilingScheme: new GeographicTilingScheme({ ellipsoid }),
              credit: moon
                ? "NASA LRO LOLA · global 4 ppd"
                : "NASA MOLA · global 4 ppd + Jezero 128 ppd",
              callback: (x, y, l) =>
                l > max
                  ? undefined
                  : pixels(
                      asset(
                        `${moon ? "unified/moon" : "mola"}/${l}/${x}/${y}.png`,
                      ),
                      c.signal,
                      size,
                      size,
                    ).then((data) => {
                      wakeUntil.current = performance.now() + 4000;
                      return decodeMola(data);
                    }),
            });
            provider.getTileDataAvailable = (x, y, l) =>
              l <= base || (!moon && available.has(`${l}/${x}/${y}`));
            const ge = provider.getLevelMaximumGeometricError.bind(provider);
            provider.getLevelMaximumGeometricError = (l) =>
              l >= max ? 0 : ge(l);
            install(
              provider,
              moon
                ? "LOLA global · muestreo ~7,6 km"
                : "MOLA global ~14,8 km · Jezero ~463 m",
            );
          })
          .catch(() => {
            if (!disposed)
              setStatus("Relieve global ausente · globo de contexto");
          });
      handler = new ScreenSpaceEventHandler(v.scene.canvas);
      handler.setInputAction((e: { position: Cartesian2 }) => {
        const hit = v?.scene.pick(e.position),
          entity = hit?.id;
        if (entity instanceof Entity && entity.id.startsWith("location:"))
          props.current.choose(entity.id.slice(9));
        else if (Array.isArray(entity) && v) {
          const points = entity
            .map((item: Entity) =>
              item.position?.getValue(v!.clock.currentTime),
            )
            .filter(Boolean) as Cartesian3[];
          if (points.length)
            v.camera.flyToBoundingSphere(BoundingSphere.fromPoints(points), {
              duration: 0,
              offset: new HeadingPitchRange(
                0,
                -Math.PI / 2,
                Math.max(30000, BoundingSphere.fromPoints(points).radius * 4),
              ),
            });
        }
      }, ScreenSpaceEventType.LEFT_CLICK);
      let last = 0;
      removeCamera = v.scene.postRender.addEventListener(() => {
        if (!v || disposed || performance.now() - last < 400) return;
        last = performance.now();
        setHeading((v.camera.heading * 180) / Math.PI);
        const current = props.current;
        contextBody.show =
          current.mode === "space" && !v.scene.globe.tilesLoaded;
        setContextOnly(contextBody.show);
        if (current.mode !== "mesh") {
          const occluder = new EllipsoidalOccluder(
            ellipsoid,
            v.camera.positionWC,
          );
          const visible = current.marks.flatMap((m) => {
            const point = Cartesian3.fromDegrees(
              m.longitude,
              m.latitude,
              0,
              ellipsoid,
            );
            const xy = v!.scene.cartesianToCanvasCoordinates(point);
            return xy &&
              occluder.isPointVisible(point) &&
              xy.x > 10 &&
              xy.y > 10 &&
              xy.x < v!.scene.canvas.clientWidth - 10 &&
              xy.y < v!.scene.canvas.clientHeight - 10
              ? [{ ...m, x: Math.round(xy.x), y: Math.round(xy.y) }]
              : [];
          });
          // Clustered points retain Cesium's cluster control; isolated map targets are
          // also real keyboard buttons, at their projected geospatial positions.
          const targets = groupMapPoints(visible, current.selected);
          setMapButtons((previous) =>
            JSON.stringify(previous) === JSON.stringify(targets)
              ? previous
              : targets,
          );
        } else setMapButtons((previous) => (previous.length ? [] : previous));
        if (props.current.mode !== "regional") {
          setScale(null);
          return;
        }
        const canvas = v.scene.canvas,
          x = canvas.clientWidth / 2,
          y = canvas.clientHeight * 0.7;
        const a = v.camera.getPickRay(new Cartesian2(x - 50, y)),
          b = v.camera.getPickRay(new Cartesian2(x + 50, y));
        const aa =
            (a && v.scene.globe.pick(a, v.scene)) ||
            (v.scene.pickPositionSupported &&
              v.scene.pickPosition(new Cartesian2(x - 50, y))),
          bb =
            (b && v.scene.globe.pick(b, v.scene)) ||
            (v.scene.pickPositionSupported &&
              v.scene.pickPosition(new Cartesian2(x + 50, y)));
        if (aa && bb)
          setScale(
            metricScale(
              new EllipsoidGeodesic(
                Cartographic.fromCartesian(aa, ellipsoid),
                Cartographic.fromCartesian(bb, ellipsoid),
                ellipsoid,
              ).surfaceDistance / 100,
            ),
          );
        else setScale(null);
      });
      removeRender = v.scene.renderError.addEventListener(() => {
        if (!disposed)
          setError(
            "El visor no pudo renderizar esta escena. La lista y las medidas siguen disponibles.",
          );
      });
      setReady(true);
      // A bounded render loop settles asynchronous globe/Canvas textures in Safari.
      // Pause offscreen/hidden scenes, and cap the paired view at 30 fps.
      let onscreen = true,
        failed = false;
      const observer = new IntersectionObserver((entries) => {
        onscreen = entries[0]?.isIntersecting ?? false;
      });
      observer.observe(root.current);
      const timer = window.setInterval(() => {
        if (
          disposed ||
          !v ||
          failed ||
          !onscreen ||
          (document.visibilityState !== "visible" &&
            performance.now() > wakeUntil.current)
        )
          return;
        try {
          v.resize();
          v.render();
        } catch {
          failed = true;
          setError(
            "El renderizador se detuvo. Recarga el visor o usa la lista de ubicaciones.",
          );
        }
      }, 1000 / 30);
      c.signal.addEventListener("abort", () => {
        clearInterval(timer);
        observer.disconnect();
      });
    } catch {
      setError(
        "WebGL no disponible. Utiliza la lista accesible de ubicaciones.",
      );
    }
    return () => {
      disposed = true;
      c.abort();
      handler?.destroy();
      removeCamera?.();
      removeRender?.();
      view.current = undefined;
      terrainMesh.current = undefined;
      guides.current = undefined;
      details.current = undefined;
      if (v && !v.isDestroyed()) v.destroy();
    };
  }, [p.body]);
  useEffect(() => {
    wakeUntil.current = performance.now() + 4000;
  }, [
    p.mode,
    p.longitude,
    p.latitude,
    p.grid,
    p.layer,
    p.exaggeration,
    p.selected,
    p.overview,
    frame,
  ]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v) return;
    const ds = new CustomDataSource("Ubicaciones");
    ds.clustering.enabled = true;
    ds.clustering.pixelRange = 42;
    ds.clustering.minimumClusterSize = 2;
    ds.clustering.clusterEvent.addEventListener(
      (entities: Entity[], cluster: any) => {
        cluster.label.show = false;
        cluster.label.text = String(entities.length);
        cluster.label.font = "600 14px DM Sans";
        cluster.label.fillColor = Color.fromCssColorString("#F6EDE0");
        cluster.label.showBackground = true;
        cluster.label.backgroundColor = Color.fromCssColorString("#34261C");
        cluster.label.id = entities;
        cluster.billboard.show = false;
        cluster.point.show = false;
        cluster.point.pixelSize = 24;
        cluster.point.color = Color.fromCssColorString(colors[p.body]);
        cluster.point.id = entities;
      },
    );
    const e = v.scene.globe.ellipsoid;
    let selectedEntity: Entity | undefined;
    for (const m of p.marks) {
      const selected = m.id === p.selected;
      const item = {
        id: `location:${m.id}`,
        position: Cartesian3.fromDegrees(m.longitude, m.latitude, 0, e),
        point: {
          pixelSize: selected ? 15 : 10,
          color: Color.fromCssColorString(
            selected ? "#F2A64E" : colors[p.body],
          ),
          outlineColor: Color.fromCssColorString("#1C1511"),
          outlineWidth: 2,
          disableDepthTestDistance: Infinity,
        },
        label: {
          text: m.name,
          font: "500 12px DM Sans",
          pixelOffset: new Cartesian2(0, -22),
          fillColor: Color.fromCssColorString("#F6EDE0"),
          showBackground: true,
          backgroundColor: Color.fromCssColorString("#271D16dd"),
          disableDepthTestDistance: Infinity,
        },
      };
      if (selected) selectedEntity = v.entities.add(item);
      else ds.entities.add(item);
    }
    void v.dataSources.add(ds);
    draw(v);
    return () => {
      if (!v.isDestroyed()) {
        v.dataSources.remove(ds, true);
        if (selectedEntity) v.entities.remove(selectedEntity);
      }
    };
  }, [ready, p.marks, p.selected, p.body]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v || p.mode !== "regional") return;
    const ds = new CustomDataSource("Huellas de estudio"),
      e = v.scene.globe.ellipsoid;
    for (const half of [1500, 900]) {
      const corners = [
        [-half, -half],
        [half, -half],
        [half, half],
        [-half, half],
        [-half, -half],
      ];
      const positions = corners.slice(0, -1).flatMap(([x, y], edge) =>
        Array.from({ length: 11 }, (_, i) => {
          const xx = x + ((corners[edge + 1][0] - x) * i) / 10,
            yy = y + ((corners[edge + 1][1] - y) * i) / 10;
          const [lon, lat] = offsetDegrees(
            p.longitude,
            p.latitude,
            xx,
            yy,
            e.maximumRadius,
          );
          const grid = p.grid,
            site = grid?.site;
          const ix = site
              ? Math.round((xx + site.window_m / 2) / site.cell_m)
              : 0,
            iy = site ? Math.round((site.window_m / 2 - yy) / site.cell_m) : 0;
          const height =
            grid && site ? grid.heights[iy * site.width + ix] : NaN;
          return Cartesian3.fromDegrees(
            lon,
            lat,
            (Number.isFinite(height) ? height : (site?.center_m ?? 0)) *
              p.exaggeration +
              35,
            e,
          );
        }),
      );
      ds.entities.add({
        polyline: {
          positions,
          width: half === 1500 ? 2 : 1,
          material: Color.fromCssColorString(
            half === 1500 ? "#F2A64E" : "#F6EDE0",
          ),
          clampToGround: false,
        },
      });
    }
    ds.entities.add({
      position: Cartesian3.fromDegrees(
        p.longitude,
        p.latitude,
        (p.grid?.site.center_m ?? 0) * p.exaggeration + 50,
        e,
      ),
      label: {
        text: "3 km · análisis / 1,8 km · visual",
        font: "11px DM Sans",
        pixelOffset: new Cartesian2(0, 25),
        showBackground: true,
        backgroundColor: Color.fromCssColorString("#271D16dd"),
        disableDepthTestDistance: Infinity,
      },
    });
    void v.dataSources.add(ds);
    draw(v);
    return () => {
      if (!v.isDestroyed()) v.dataSources.remove(ds, true);
    };
  }, [ready, p.mode, p.longitude, p.latitude, p.grid, p.exaggeration, p.body]);
  useEffect(() => {
    const v = view.current;
    if (!ready || !v || p.mode !== "regional" || p.body === "Moon") return;
    let disposed = false,
      layer: ImageryLayer | undefined;
    const task =
      p.body === "Earth"
        ? ArcGisMapServerImageryProvider.fromUrl(
            "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer",
          )
        : SingleTileImageryProvider.fromUrl(asset("jezero-ctx-regional.png"), {
            ellipsoid: v.scene.globe.ellipsoid,
            rectangle: Rectangle.fromDegrees(
              76.640625,
              17.578125,
              78.75,
              19.6875,
            ),
            credit: "NASA CTX / Esri · recorte ~81 m/píxel",
          });
    task
      .then((provider) => {
        if (!disposed && !v.isDestroyed()) {
          layer = new ImageryLayer(provider);
          v.imageryLayers.add(layer);
          details.current = layer;
          draw(v);
        }
      })
      .catch(() => {
        if (!disposed)
          setError(
            "Imagen regional sin servicio. Se conserva el contexto y el DEM disponible.",
          );
      });
    return () => {
      disposed = true;
      if (layer && !v.isDestroyed()) v.imageryLayers.remove(layer);
      details.current = undefined;
    };
  }, [ready, p.mode, p.body]);
  useEffect(() => {
    const v = view.current;
    if (!v || !ready || !p.grid || p.mode === "space") return;
    const regional = p.mode === "regional";
    // Regional lunar and terrestrial patches use absolute heights on the curved body.
    // Local paired patches use median-relative elevation, preserving real horizontal distances.

    const { site: s, heights: h } = p.grid,
      a = meshArrays(h, s, p.exaggeration),
      e = v.scene.globe.ellipsoid;
    let matrix = Matrix4.IDENTITY;
    if (regional) {
      for (let i = 0; i < h.length; i++) {
        const x = a.positions[i * 3],
          y = a.positions[i * 3 + 1];
        const [lon, lat] = offsetDegrees(
          s.longitude,
          s.latitude,
          x,
          y,
          e.maximumRadius,
        );
        const point = Cartesian3.fromDegrees(
          lon,
          lat,
          Number.isFinite(h[i]) ? h[i] * p.exaggeration : 0,
          e,
        );
        a.positions.set([point.x, point.y, point.z], i * 3);
        if (p.body === "Mars")
          a.uv.set(
            [
              (lon - 76.640625) / (78.75 - 76.640625),
              (lat - 17.578125) / (19.6875 - 17.578125),
            ],
            i * 2,
          );
      }
    } else
      matrix = Transforms.eastNorthUpToFixedFrame(
        Cartesian3.fromDegrees(s.longitude, s.latitude, 0, e),
        e,
      );
    const geometry = GeometryPipeline.computeNormal(
      new Geometry({
        attributes: Object.assign(new GeometryAttributes(), {
          position: new GeometryAttribute({
            componentDatatype: ComponentDatatype.DOUBLE,
            componentsPerAttribute: 3,
            values: a.positions,
          }),
          st: new GeometryAttribute({
            componentDatatype: ComponentDatatype.FLOAT,
            componentsPerAttribute: 2,
            values: a.uv,
          }),
        }),
        indices: a.indices,
        primitiveType: PrimitiveType.TRIANGLES,
        boundingSphere: BoundingSphere.fromVertices(a.positions),
      }),
    );
    const values = visualValues(p.grid, regional ? "elevation" : p.layer),
      range = regional ? [s.min_m - s.center_m, s.max_m - s.center_m] : p.range;
    const canvas = document.createElement("canvas");
    canvas.width = s.width;
    canvas.height = s.height;
    const ctx = canvas.getContext("2d")!,
      rgba = ctx.createImageData(s.width, s.height);
    values.forEach((h, i) => {
      if (Number.isFinite(h))
        rgba.data.set([...elevationColor(h, range[0], range[1]), 255], i * 4);
    });
    ctx.putImageData(rgba, 0, 0);
    const mesh = v.scene.primitives.add(
      new Primitive({
        geometryInstances: new GeometryInstance({
          geometry,
          modelMatrix: matrix,
        }),
        appearance: new MaterialAppearance({
          material: Material.fromType("Image", {
            image:
              regional && p.body === "Mars"
                ? asset("jezero-ctx-regional.png")
                : canvas,
          }),
          translucent: false,
          faceForward: true,
          closed: false,
        }),
        asynchronous: false,
      }),
    );
    terrainMesh.current = mesh;
    let guide: CustomDataSource | undefined;
    if (!regional) {
      guide = localGuides(s, h, p.exaggeration, matrix);
      guides.current = guide;
      void v.dataSources.add(guide);
    }
    draw(v);
    return () => {
      if (!v.isDestroyed()) {
        v.scene.primitives.remove(mesh);
        if (guide) v.dataSources.remove(guide, true);
      }
      terrainMesh.current = undefined;
      guides.current = undefined;
    };
  }, [
    ready,
    p.grid,
    p.mode,
    p.layer,
    p.range[0],
    p.range[1],
    p.exaggeration,
    p.body,
  ]);
  useEffect(() => {
    const v = view.current;
    if (!v || !ready) return;
    const local = p.mode === "mesh",
      e = v.scene.globe.ellipsoid;
    v.scene.globe.show = !local;
    v.entities.show = !local;
    if (guides.current) guides.current.show = local;
    for (let i = 0; i < v.dataSources.length; i++)
      v.dataSources.get(i).show = local
        ? v.dataSources.get(i) === guides.current
        : true;
    v.scene.screenSpaceCameraController.enableCollisionDetection = !local;
    v.scene.verticalExaggeration = p.exaggeration;
    v.camera.cancelFlight();
    v.camera.lookAtTransform(Matrix4.IDENTITY);
    const center = Cartesian3.fromDegrees(
      p.longitude,
      p.latitude,
      local ? 0 : (p.grid?.site.center_m ?? 0),
      e,
    );
    if (local)
      v.camera.lookAtTransform(
        Transforms.eastNorthUpToFixedFrame(center, e),
        new HeadingPitchRange(0, CMath.toRadians(-48), 4000),
      );
    else if (p.mode === "space")
      v.camera.setView({
        destination: Cartesian3.fromDegrees(
          p.overview ? 0 : p.longitude,
          p.overview && p.body === "Moon" ? -65 : p.latitude,
          e.maximumRadius * 2.1,
          e,
        ),
      });
    else {
      v.camera.lookAt(
        center,
        new HeadingPitchRange(0, CMath.toRadians(-55), 44000),
      );
      v.camera.lookAtTransform(Matrix4.IDENTITY);
    }
    draw(v);
  }, [
    ready,
    p.mode,
    p.longitude,
    p.latitude,
    p.overview,
    p.body,
    frame,
    p.grid?.site.center_m,
  ]);
  useEffect(() => {
    const v = view.current;
    if (ready && v) {
      v.scene.verticalExaggeration = p.exaggeration;
      draw(v);
    }
  }, [ready, p.exaggeration]);
  return (
    <div className="u-scene">
      <div
        ref={root}
        className="u-canvas"
        role="region"
        aria-label={`Mapa 3D de ${p.name}`}
      />
      {p.mode !== "mesh" &&
        mapButtons.map((m) => (
          <button
            key={m.id}
            className={`u-map-marker u-${p.body}`}
            style={{ left: m.x, top: m.y }}
            aria-label={
              m.members.length > 1
                ? `Ampliar grupo de ${m.members.length} ${p.body === "Earth" ? "candidatas" : "referencias"} en el mapa`
                : `Seleccionar ${p.body === "Earth" ? "candidata" : "referencia"} ${m.name} en el mapa`
            }
            aria-pressed={m.id === p.selected}
            onClick={() => {
              if (m.members.length === 1) {
                p.choose(m.id);
                return;
              }
              const v = view.current;
              if (!v) return;
              const e = v.scene.globe.ellipsoid;
              const points = p.marks
                .filter((mark) => m.members.includes(mark.id))
                .map((mark) =>
                  Cartesian3.fromDegrees(mark.longitude, mark.latitude, 0, e),
                );
              const sphere = BoundingSphere.fromPoints(points);
              v.camera.lookAt(
                sphere.center,
                new HeadingPitchRange(
                  0,
                  -Math.PI / 2,
                  Math.max(30000, sphere.radius * 3),
                ),
              );
              v.camera.lookAtTransform(Matrix4.IDENTITY);
              wakeUntil.current = performance.now() + 4000;
              draw(v);
            }}
          >
            {p.body === "Earth" || m.members.length > 1 ? (
              m.name
            ) : (
              <span aria-hidden="true">•</span>
            )}
          </button>
        ))}
      <div className="u-scene-top">
        <span className={`u-body u-${p.body}`}>
          {p.body === "Mars" ? "MARTE" : p.body === "Moon" ? "LUNA" : "TIERRA"}
        </span>
        <span>
          {p.mode === "mesh"
            ? "Malla DEM · 1,8 × 1,8 km"
            : p.mode === "regional"
              ? "Encuadre regional · ~24 km"
              : contextOnly
                ? "Contexto NASA · relieve global pendiente"
                : status}
        </span>
      </div>
      <button
        className="u-reset"
        onClick={() => setFrame((n) => n + 1)}
        aria-label={`Restablecer encuadre de ${p.name}`}
      >
        ⌖
      </button>
      {p.mode !== "space" && (
        <span
          className="u-north"
          style={{ transform: `rotate(${-heading}deg)` }}
        >
          N ↑
        </span>
      )}
      {p.mode === "regional" && scale && (
        <div className="u-ruler">
          <span style={{ width: scale.pixels }} />
          {scale.distance >= 1000
            ? `${scale.distance / 1000} km`
            : `${scale.distance} m`}
        </div>
      )}
      {p.mode === "mesh" && !p.grid && (
        <div className="u-missing" role="status">
          <strong>
            {p.pending
              ? "Leyendo DEM de esta ubicación…"
              : "Sin malla local disponible"}
          </strong>
          <p>
            {p.pending
              ? "Se cargará únicamente el relieve de la selección actual."
              : p.missing || "El DEM de esta ubicación no está publicado."}
          </p>
          <small>La selección y las medidas del motor se conservan.</small>
        </div>
      )}
      {error && (
        <p className="u-map-error" role="alert">
          {error}
        </p>
      )}
      <span className="u-gesture">
        Arrastra para explorar · rueda para acercar
      </span>
    </div>
  );
}
