/** Decode as data, without color conversion or premultiplied alpha. */
export async function pixels(
  url: string,
  signal: AbortSignal,
  width: number,
  height: number,
) {
  const response = await fetch(url, { signal }).catch((error) => {
    if (signal.aborted) throw error;
    throw new Error("No se pudo descargar la cuadrícula de elevación.");
  });
  if (!response.ok)
    throw new Error("No se pudo descargar la cuadrícula de elevación.");
  if (!response.headers.get("content-type")?.startsWith("image/"))
    throw new Error("La fuente no devolvió una imagen DEM válida.");
  const bitmap = await createImageBitmap(await response.blob(), {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  }).catch((error) => {
    if (signal.aborted) throw error;
    throw new Error("No se pudo decodificar la imagen del DEM.");
  });
  try {
    if (bitmap.width !== width || bitmap.height !== height)
      throw new Error("La imagen no coincide con la cuadrícula declarada.");
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("No se pudo leer el mapa de alturas.");
    ctx.drawImage(bitmap, 0, 0);
    return ctx.getImageData(0, 0, width, height).data;
  } finally {
    bitmap.close();
  }
}
