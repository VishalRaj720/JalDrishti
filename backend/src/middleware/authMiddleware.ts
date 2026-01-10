import { Request, Response, NextFunction } from 'express';
import { verifyAccessToken, extractTokenFromHeader } from '../utils/jwt';
import { User } from '../models';

// Extend Express Request type to include user
declare global {
    namespace Express {
        interface Request {
            user?: {
                userId: string;
                email: string;
                role: string;
            };
        }
    }
}

/**
 * Middleware to authenticate requests using JWT
 */
export const authenticate = async (
    req: Request,
    res: Response,
    next: NextFunction
): Promise<void> => {
    try {
        const token = extractTokenFromHeader(req.headers.authorization);

        if (!token) {
            res.status(401).json({ error: 'No token provided' });
            return;
        }

        const payload = verifyAccessToken(token);

        // Verify user still exists
        const user = await User.findByPk(payload.userId);
        if (!user) {
            res.status(401).json({ error: 'User not found' });
            return;
        }

        // Attach user info to request
        req.user = {
            userId: payload.userId,
            email: payload.email,
            role: payload.role,
        };

        next();
    } catch (error) {
        res.status(401).json({ error: 'Invalid or expired token' });
    }
};

/**
 * Optional authentication - doesn't fail if no token
 */
export const optionalAuthenticate = async (
    req: Request,
    res: Response,
    next: NextFunction
): Promise<void> => {
    try {
        const token = extractTokenFromHeader(req.headers.authorization);

        if (token) {
            const payload = verifyAccessToken(token);
            const user = await User.findByPk(payload.userId);

            if (user) {
                req.user = {
                    userId: payload.userId,
                    email: payload.email,
                    role: payload.role,
                };
            }
        }

        next();
    } catch (error) {
        // Continue without authentication
        next();
    }
};
