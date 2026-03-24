export type UserRole = 'admin' | 'analyst' | 'viewer';

export interface User {
    id: string;
    username: string;
    email: string;
    role: UserRole;
    created_at: string;
    updated_at: string;
}

export interface AuthTokens {
    access_token: string;
    refresh_token: string;
    token_type: 'bearer';
}

export interface LoginRequest {
    username: string;   // FastAPI OAuth2 form field name
    password: string;
}
