import { Sequelize } from 'sequelize';
import { config } from './env';

// Create Sequelize instance
export const sequelize = new Sequelize({
    host: config.DB_HOST,
    port: config.DB_PORT,
    database: config.DB_NAME,
    username: config.DB_USER,
    password: config.DB_PASSWORD,
    dialect: 'postgres',
    logging: config.NODE_ENV === 'development' ? console.log : false,
    pool: {
        max: 10,
        min: 0,
        acquire: 30000,
        idle: 10000,
    },
    define: {
        timestamps: true,
        underscored: true,
    },
});

// Test database connection
export const testConnection = async (): Promise<void> => {
    try {
        await sequelize.authenticate();
        console.log('✓ Database connection established successfully');
    } catch (error) {
        console.error('✗ Unable to connect to the database:', error);
        throw error;
    }
};

// Sync database (use migrations in production)
export const syncDatabase = async (force = false): Promise<void> => {
    try {
        await sequelize.sync({ force, alter: config.NODE_ENV === 'development' });
        console.log('✓ Database synchronized');
    } catch (error) {
        console.error('✗ Database sync failed:', error);
        throw error;
    }
};
