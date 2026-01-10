import dotenv from 'dotenv';
import path from 'path';

// Load environment variables
dotenv.config({ path: path.join(__dirname, '../../.env') });

interface EnvConfig {
    NODE_ENV: string;
    PORT: number;

    // Database
    DB_HOST: string;
    DB_PORT: number;
    DB_NAME: string;
    DB_USER: string;
    DB_PASSWORD: string;

    // JWT
    JWT_SECRET: string;
    JWT_EXPIRES_IN: string;
    JWT_REFRESH_SECRET: string;
    JWT_REFRESH_EXPIRES_IN: string;

    // CORS
    CORS_ORIGIN: string;
}

const getEnv = (key: string, defaultValue?: string): string => {
    const value = process.env[key] || defaultValue;
    if (!value) {
        throw new Error(`Missing environment variable: ${key}`);
    }
    return value;
};

export const config: EnvConfig = {
    NODE_ENV: getEnv('NODE_ENV', 'development'),
    PORT: parseInt(getEnv('PORT', '5000'), 10),

    DB_HOST: getEnv('DB_HOST', 'localhost'),
    DB_PORT: parseInt(getEnv('DB_PORT', '5432'), 10),
    DB_NAME: getEnv('DB_NAME', 'groundwater_db'),
    DB_USER: getEnv('DB_USER', 'postgres'),
    DB_PASSWORD: getEnv('DB_PASSWORD', 'postgres'),

    JWT_SECRET: getEnv('JWT_SECRET', 'your-secret-key-change-in-production'),
    JWT_EXPIRES_IN: getEnv('JWT_EXPIRES_IN', '1h'),
    JWT_REFRESH_SECRET: getEnv('JWT_REFRESH_SECRET', 'your-refresh-secret-change-in-production'),
    JWT_REFRESH_EXPIRES_IN: getEnv('JWT_REFRESH_EXPIRES_IN', '7d'),

    CORS_ORIGIN: getEnv('CORS_ORIGIN', 'http://localhost:5173'),
};
