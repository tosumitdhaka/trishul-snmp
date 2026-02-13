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
                clientPort: 8080
            },
            watch: {
                usePolling: true, // Needed for Docker
                interval: 100
            }
        },

        // Preview server (production build testing)
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
                        // Vendor chunk for third-party dependencies
                        vendor: ['bootstrap'],
                        
                        // Core application modules
                        core: [
                            './src/js/core/router.js',
                            './src/js/core/auth.js',
                            './src/js/core/api.js',
                            './src/js/core/store.js',
                            './src/js/core/component.js'
                        ],
                        
                        // UI components
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
            
            // Chunk size warnings
            chunkSizeWarningLimit: 1000,
            
            // CSS code splitting
            cssCodeSplit: true,
            
            // Asset inlining (small assets as base64)
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
            preprocessorOptions: {
                // Add if using SCSS later
            }
        },

        // Logging
        logLevel: isDev ? 'info' : 'warn',
        clearScreen: false
    };
});
