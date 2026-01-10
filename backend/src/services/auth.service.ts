import { User } from '../models';
import { generateTokens, verifyRefreshToken, JwtPayload, TokenPair } from '../utils/jwt';
import { AppError } from '../middleware/errorHandler';

interface RegisterData {
    email: string;
    password: string;
    name: string;
    role?: 'admin' | 'analyst' | 'viewer';
}

interface LoginData {
    email: string;
    password: string;
}

export class AuthService {
    /**
     * Register a new user
     */
    static async register(data: RegisterData): Promise<{ user: User; tokens: TokenPair }> {
        const { email, password, name, role = 'viewer' } = data;

        // Check if user already exists
        const existingUser = await User.findOne({ where: { email } });
        if (existingUser) {
            throw new AppError('User with this email already exists', 409);
        }

        // Hash password
        const passwordHash = await User.hashPassword(password);

        // Create user
        const user = await User.create({
            email,
            passwordHash,
            name,
            role,
        });

        // Generate tokens
        const payload: JwtPayload = {
            userId: user.id,
            email: user.email,
            role: user.role,
        };
        const tokens = generateTokens(payload);

        return { user, tokens };
    }

    /**
     * Login user
     */
    static async login(data: LoginData): Promise<{ user: User; tokens: TokenPair }> {
        const { email, password } = data;

        // Find user
        const user = await User.findOne({ where: { email } });
        if (!user) {
            throw new AppError('Invalid credentials', 401);
        }

        // Check password
        const isPasswordValid = await user.comparePassword(password);
        if (!isPasswordValid) {
            throw new AppError('Invalid credentials', 401);
        }

        // Generate tokens
        const payload: JwtPayload = {
            userId: user.id,
            email: user.email,
            role: user.role,
        };
        const tokens = generateTokens(payload);

        return { user, tokens };
    }

    /**
     * Refresh access token
     */
    static async refreshToken(refreshToken: string): Promise<TokenPair> {
        try {
            const payload = verifyRefreshToken(refreshToken);

            // Verify user still exists
            const user = await User.findByPk(payload.userId);
            if (!user) {
                throw new AppError('User not found', 401);
            }

            // Generate new tokens
            const newPayload: JwtPayload = {
                userId: user.id,
                email: user.email,
                role: user.role,
            };
            return generateTokens(newPayload);
        } catch (error) {
            throw new AppError('Invalid refresh token', 401);
        }
    }

    /**
     * Get user by ID
     */
    static async getUserById(userId: string): Promise<User> {
        const user = await User.findByPk(userId);
        if (!user) {
            throw new AppError('User not found', 404);
        }
        return user;
    }
}
