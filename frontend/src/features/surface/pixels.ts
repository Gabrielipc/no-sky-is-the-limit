import { tr } from "../../i18n/lang";
/** Decode as data, without color conversion or premultiplied alpha. */
export async function pixels(
  url: string,
  signal: AbortSignal,
  width: number,
  height: number,
) {
  const response = await fetch(url, { signal }).catch((error) => {
    if (signal.aborted) throw error;
    throw new Error(tr("No se pudo descargar la cuadrícula de elevación.", "The elevation grid could not be downloaded."));
  });
  if (!response.ok)
    throw new Error(tr("No se pudo descargar la cuadrícula de elevación.", "The elevation grid could not be downloaded."));
  if (!response.headers.get("content-type")?.startsWith("image/"))
    throw new Error(tr("La fuente no devolvió una imagen DEM válida.", "The source did not return a valid DEM image."));
  const bitmap = await createImageBitmap(await response.blob(), {
    colorSpaceConversion: "none",
    premultiplyAlpha: "none",
  }).catch((error) => {
    if (signal.aborted) throw error;
    throw new Error(tr("No se pudo decodificar la imagen del DEM.", "The DEM image could not be decoded."));
  });
  try {
    if (bitmap.width !== width || bitmap.height !== height)
      throw new Error(tr("La imagen no coincide con la cuadrícula declarada.", "The image does not match the declared grid."));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error(tr("No se pudo leer el mapa de alturas.", "The height map could not be read."));
    ctx.drawImage(bitmap, 0, 0);
    return ctx.getImageData(0, 0, width, height).data;
  } finally {
    bitmap.close();
  }
}
