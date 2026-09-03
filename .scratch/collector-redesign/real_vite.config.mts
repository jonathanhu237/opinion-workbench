import base from '../../frontend/vite.config.ts'

export default {
  ...base,
  server: {
    ...base.server,
    host: '127.0.0.1',
    port: 15175,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:18143', changeOrigin: false },
    },
  },
}
