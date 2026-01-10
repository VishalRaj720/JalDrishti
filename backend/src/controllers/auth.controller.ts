import { Request, Response, NextFunction } from 'express';
import { AuthService } from '../services/auth.service';
import Joi from 'joi';
import { logger } from '../utils/logger';

// Validation schemas
const registerSchema = Joi.object({
    email: Joi.string().email().required(),
    password: Joi.string().min(6).required(),
    name: Joi.string().min(2).required(),
    role: Joi.string().valid('admin', 'analyst', 'viewer').optional(),
});

const loginSchema = Joi.object({
    email: Joi.string().email().required(),
    password: Joi.string().required(),
});

const refreshSchema = Joi.object({
    refreshToken: Joi.string().required(),
});

export class AuthController {
    /**
     * Register a new user
     */
    static async register(req: Request, res: Response, next: NextFunction): Promise<void> {
        try {
            const { error, value } = registerSchema.validate(req.body);
            if (error) {
                res.status(400).json({ error: error.details[0].message });
                return;
            }

            const { user, tokens } = await AuthService.register(value);

            logger.info(`User registered: ${user.email}`);

            console.log(user);

            res.status(201).json({
                message: 'User registered successfully',
                user: {
                    id: user.id,
                    email: user.email,
                    name: user.name,
                    role: user.role,
                },
                tokens,
            });
        } catch (error: any) {
            next(error.message);
            console.log(error.message);
        }
    }

    /**
     * Login user
     */
    static async login(req: Request, res: Response, next: NextFunction): Promise<void> {
        try {
            const { error, value } = loginSchema.validate(req.body);
            if (error) {
                res.status(400).json({ error: error.details[0].message });
                return;
            }

            const { user, tokens } = await AuthService.login(value);

            logger.info(`User logged in: ${user.email}`);

            console.log(user);

            res.json({
                message: 'Login successful',
                user: {
                    id: user.id,
                    email: user.email,
                    name: user.name,
                    role: user.role,
                },
                tokens,
            });
        } catch (error: any) {
            next(error.message);
            console.log(error.message);

        }
    }

    /**
     * Refresh access token
     */
    static async refresh(req: Request, res: Response, next: NextFunction): Promise<void> {
        try {
            const { error, value } = refreshSchema.validate(req.body);
            if (error) {
                res.status(400).json({ error: error.details[0].message });
                return;
            }

            const tokens = await AuthService.refreshToken(value.refreshToken);

            res.json({
                message: 'Token refreshed successfully',
                tokens,
            });
        } catch (error) {
            next(error);
        }
    }

    /**
     * Get current user
     */
    static async me(req: Request, res: Response, next: NextFunction): Promise<void> {
        try {
            if (!req.user) {
                res.status(401).json({ error: 'Not authenticated' });
                return;
            }

            const user = await AuthService.getUserById(req.user.userId);

            res.json({
                user: {
                    id: user.id,
                    email: user.email,
                    name: user.name,
                    role: user.role,
                },
            });
        } catch (error) {
            next(error);
        }
    }

    /**
     * Logout (client-side token removal)
     */
    static async logout(req: Request, res: Response): Promise<void> {
        res.json({ message: 'Logout successful' });
    }
}
