export interface User {
    id: string;
    email: string;
    name: string;
    role: 'admin' | 'analyst' | 'viewer';
}

export interface LoginCredentials {
    email: string;
    password: string;
}

export interface RegisterData {
    email: string;
    password: string;
    name: string;
}

export interface TokenPair {
    accessToken: string;
    refreshToken: string;
}

export interface AuthResponse {
    user: User;
    tokens: TokenPair;
}
