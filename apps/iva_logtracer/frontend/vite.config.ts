import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { federation } from '@module-federation/vite'
import { resolve } from 'path'
import services from '../../../config/services.js'

const SERVICE_NAME = 'iva-logtracer'
const port = services.services[SERVICE_NAME]?.frontend?.port ?? 5192

export default defineConfig({
    plugins: [
        react(),
        federation({
            name: 'iva_logtracer',
            filename: 'remoteEntry.js',
            manifest: true,
            exposes: {
                './App': './src/App.tsx',
            },
            shared: {
                react: { singleton: true },
                'react-dom': { singleton: true },
                'react-router-dom': { singleton: true },
                '@tanstack/react-query': { singleton: true },
                '@cptools/ui': { singleton: true },
            },
        }) as any,
    ],
    resolve: {
        alias: {
            '@': resolve(__dirname, './src'),
        },
    },
    server: {
        port,
        hmr: { clientPort: services.gateway.port },
        host: true,
        cors: true,
        allowedHosts: services.external.allowedHosts,
        proxy: {
            // Proxy API requests to nginx gateway for standalone development
            '/api': {
                target: `http://localhost:${services.gateway.port}`,
                changeOrigin: true,
            },
        },
    },
    base: `/mfe/${SERVICE_NAME}/`,
    build: {
        target: 'chrome89',
        minify: false,
        cssCodeSplit: false,
    },
    // 预先声明需要优化的依赖，避免运行时优化导致 "factory is not a function" 错误
    optimizeDeps: {
        include: [
            'react',
            'react-dom',
            '@tanstack/react-query',
        ],
    },
})
