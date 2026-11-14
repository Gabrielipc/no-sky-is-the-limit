import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import cesium from 'vite-plugin-cesium';
// Keep the asset copying / worker paths, but load Cesium only when location opens.
const cesiumAssets = cesium();
export default defineConfig({
  plugins: [react(), { ...cesiumAssets, transformIndexHtml: () => [] }],
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
});
