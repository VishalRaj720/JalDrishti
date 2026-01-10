import app from './app';
import { config } from './config/env';
import { testConnection, syncDatabase } from './config/db';
import { logger } from './utils/logger';

const startServer = async (): Promise<void> => {
    try {
        // Test database connection
        await testConnection();

        // Sync database (in production, use migrations instead)
        if (config.NODE_ENV === 'development') {
            await syncDatabase(false); // Set to true to drop tables
        }

        // Start server
        const server = app.listen(config.PORT, () => {
            logger.info(`🚀 Server running on port ${config.PORT}`);
            logger.info(`📊 Environment: ${config.NODE_ENV}`);
        });

        // Graceful shutdown
        const gracefulShutdown = (signal: string) => {
            logger.info(`${signal} received. Shutting down gracefully...`);
            server.close(() => {
                logger.info('Server closed');
                process.exit(0);
            });

            // Force shutdown after 10 seconds
            setTimeout(() => {
                logger.error('Forced shutdown');
                process.exit(1);
            }, 10000);
        };

        process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
        process.on('SIGINT', () => gracefulShutdown('SIGINT'));

    } catch (error) {
        logger.error('Failed to start server:', error);
        process.exit(1);
    }
};

startServer();
