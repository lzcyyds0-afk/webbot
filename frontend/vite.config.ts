import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: {
      usePolling: true,
      interval: 300,
    },
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/screenshots': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws/socket.io': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // Vite 8's bundler (rolldown) requires manualChunks as a function,
        // not an object. Split heavy vendor groups into their own chunks.
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return;
          if (id.includes('/@monaco-editor/') || id.includes('/monaco-editor/')) return 'editor';
          if (id.includes('/antd/') || id.includes('/@ant-design/')) return 'ui';
          if (id.includes('/react-router') || id.includes('/react-dom/') || id.includes('/react/')) return 'vendor';
        },
      },
    },
  },
});