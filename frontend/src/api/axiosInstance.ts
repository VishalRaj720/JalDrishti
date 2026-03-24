import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { store } from '@/redux/store';
import { selectAccessToken, selectRefreshToken, updateToken, logout } from '@/redux/slices/authSlice';
import type { ApiError } from '@/types/common';

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api/v1';

const axiosInstance = axios.create({
    baseURL: BASE_URL,
    withCredentials: true,   // sends httpOnly refresh cookie
    headers: {
        'Content-Type': 'application/json',
    },
});

// ── Request Interceptor ───────────────────────────────────────────
axiosInstance.interceptors.request.use(
    (config: InternalAxiosRequestConfig) => {
        const token = selectAccessToken(store.getState());
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// ── Response Interceptor ──────────────────────────────────────────
let isRefreshing = false;
let refreshQueue: Array<(token: string) => void> = [];

const processQueue = (token: string) => {
    refreshQueue.forEach((resolve) => resolve(token));
    refreshQueue = [];
};

axiosInstance.interceptors.response.use(
    (response) => response,
    async (error: AxiosError) => {
        const originalRequest = error.config as InternalAxiosRequestConfig & {
            _retry?: boolean;
        };

        if (error.response?.status === 401 && !originalRequest._retry) {
            if (isRefreshing) {
                // Queue requests while a refresh is in progress
                return new Promise<string>((resolve) => {
                    refreshQueue.push(resolve);
                }).then((newToken) => {
                    originalRequest.headers.Authorization = `Bearer ${newToken}`;
                    return axiosInstance(originalRequest);
                });
            }

            originalRequest._retry = true;
            isRefreshing = true;

            try {
                const refreshToken = selectRefreshToken(store.getState());
                if (!refreshToken) {
                    // No refresh token stored — force logout immediately
                    store.dispatch(logout());
                    window.location.href = '/login';
                    return Promise.reject(new Error('No refresh token available'));
                }
                const { data } = await axios.post<{ access_token: string }>(
                    `${BASE_URL}/auth/refresh`,
                    { refresh_token: refreshToken },
                    { withCredentials: true }
                );
                const newToken = data.access_token;
                store.dispatch(updateToken(newToken));
                processQueue(newToken);
                originalRequest.headers.Authorization = `Bearer ${newToken}`;
                return axiosInstance(originalRequest);
            } catch (_refreshError) {
                refreshQueue = [];
                store.dispatch(logout());
                window.location.href = '/login';
                return Promise.reject(_refreshError);
            } finally {
                isRefreshing = false;
            }
        }

        // Parse backend error detail
        const apiError: ApiError = {
            status: error.response?.status ?? 0,
            detail:
                (error.response?.data as { detail?: string })?.detail ??
                error.message ??
                'Unknown error',
        };
        return Promise.reject(apiError);
    }
);

export default axiosInstance;
