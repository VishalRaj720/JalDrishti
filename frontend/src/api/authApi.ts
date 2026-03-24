import axiosInstance from './axiosInstance';
import type { AuthTokens, LoginRequest, User } from '@/types/user';

export const authApi = {
    login: async (credentials: LoginRequest): Promise<AuthTokens> => {
        // Backend /auth/login expects JSON body with { email, password }
        const { data } = await axiosInstance.post<AuthTokens>('/auth/login', {
            email: credentials.username,
            password: credentials.password,
        });
        return data;
    },

    getMe: async (): Promise<User> => {
        const { data } = await axiosInstance.get<User>('/auth/me');
        return data;
    },

    refresh: async (): Promise<AuthTokens> => {
        const { data } = await axiosInstance.post<AuthTokens>('/auth/refresh');
        return data;
    },

    logout: async (): Promise<void> => {
        await axiosInstance.post('/auth/logout');
    },
};
