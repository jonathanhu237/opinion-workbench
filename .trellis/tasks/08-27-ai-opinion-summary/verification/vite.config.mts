// Isolated ESM QA config: never proxy mutations to the user's running API.
import baseConfig from '../../../../frontend/vite.config.ts'

export default {
  ...baseConfig,
  server: {
    ...baseConfig.server,
    host: '127.0.0.1',
    port: 15184,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18080',
        changeOrigin: false,
      },
    },
  },
}
