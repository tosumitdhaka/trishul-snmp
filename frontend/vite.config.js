import { defineConfig } from 'vite';
import path from 'path';

export default defineConfig(({ command, mode }) => {
    const isDev = mode === 'development';
    const isProd = mode === 'production';

    return {
        root: 'src',
        base: '/',
        
        // Server configuration
        server: {
            port: 8080,
            strictPort: true,
            host: '0.0.0.0',
            proxy: {
                '/api': {
                    target: 'http://backend:8000',
                    changeOrigin: true,
                    secure: false
                }
            },
            hmr: {
                overlay: true,
                clientPort: 8080,
                // More conservative HMR
                timeout: 30000
            },
            watch: {
                usePolling: true,
                interval: 300, // Increased from 100ms to be less aggressive
                ignored: ['**/node_modules/**', '**/dist/**']
            }
        },

        // Preview server
        preview: {
            port: 8080,
            strictPort: true,
            host: '0.0.0.0',
            proxy: {
                '/api': {
                    target: 'http://backend:8000',
                    changeOrigin: true
                }
            }
        },

        // Build configuration
        build: {
            outDir: '../dist',
            emptyOutDir: true,
            sourcemap: isDev,
            minify: isProd ? 'esbuild' : false,
            target: 'es2020',
            
            rollupOptions: {
                input: {
                    main: path.resolve(__dirname, 'src/index.html')
                },
                output: {
                    manualChunks: {
                        vendor: ['bootstrap'],
                        core: [
                            './src/js/core/router.js',
                            './src/js/core/auth.js',
                            './src/js/core/api.js',
                            './src/js/core/store.js',
                            './src/js/core/component.js'
                        ],
                        components: [
                            './src/js/components/Card.js',
                            './src/js/components/Table.js',
                            './src/js/components/Alert.js',
                            './src/js/components/Modal.js'
                        ]
                    },
                    entryFileNames: 'assets/[name]-[hash].js',
                    chunkFileNames: 'assets/[name]-[hash].js',
                    assetFileNames: 'assets/[name]-[hash].[ext]'
                }
            },
            
            chunkSizeWarningLimit: 1000,
            cssCodeSplit: true,
            assetsInlineLimit: 4096
        },

        // Resolve configuration
        resolve: {
            alias: {
                '@': path.resolve(__dirname, 'src'),
                '@core': path.resolve(__dirname, 'src/js/core'),
                '@components': path.resolve(__dirname, 'src/js/components'),
                '@modules': path.resolve(__dirname, 'src/js/modules'),
                '@css': path.resolve(__dirname, 'src/css'),
                '@img': path.resolve(__dirname, 'src/img')
            },
            extensions: ['.js', '.json', '.css']
        },

        // Optimization
        optimizeDeps: {
            include: ['bootstrap'],
            exclude: []
        },

        // Environment variables
        define: {
            __DEV__: isDev,
            __PROD__: isProd,
            __BUILD_TIME__: JSON.stringify(new Date().toISOString())
        },

        // CSS configuration
        css: {
            devSourcemap: isDev,
            preprocessorOptions: {}
        },

        // Logging
        logLevel: isDev ? 'info' : 'warn',
        clearScreen: false
    };
});
