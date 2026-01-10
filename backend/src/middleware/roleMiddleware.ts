import { Request, Response, NextFunction } from 'express';
import { UserRole } from '../models/User';

/**
 * Middleware to check if user has required role
 */
export const requireRole = (...allowedRoles: UserRole[]) => {
    return (req: Request, res: Response, next: NextFunction): void => {
        if (!req.user) {
            res.status(401).json({ error: 'Authentication required' });
            return;
        }

        if (!allowedRoles.includes(req.user.role as UserRole)) {
            res.status(403).json({
                error: 'Insufficient permissions',
                required: allowedRoles,
                current: req.user.role,
            });
            return;
        }

        next();
    };
};

/**
 * Shorthand middleware for admin-only routes
 */
export const requireAdmin = requireRole('admin');

/**
 * Shorthand middleware for admin or analyst routes
 */
export const requireAnalyst = requireRole('admin', 'analyst');
