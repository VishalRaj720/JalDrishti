import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { User, UserRole } from '@/types/user';
import type { RootState } from '../store';

interface AuthState {
    user: User | null;
    accessToken: string | null;    // in-memory only – never persisted
    refreshToken: string | null;   // in-memory only – never persisted
    role: UserRole | null;
    isAuthenticated: boolean;
}

const initialState: AuthState = {
    user: null,
    accessToken: null,
    refreshToken: null,
    role: null,
    isAuthenticated: false,
};

const authSlice = createSlice({
    name: 'auth',
    initialState,
    reducers: {
        setCredentials: (
            state,
            action: PayloadAction<{ user: User; accessToken: string; refreshToken?: string }>
        ) => {
            state.user = action.payload.user;
            state.accessToken = action.payload.accessToken;
            if (action.payload.refreshToken !== undefined) {
                state.refreshToken = action.payload.refreshToken;
            }
            state.role = action.payload.user.role;
            state.isAuthenticated = true;
        },
        updateToken: (state, action: PayloadAction<string>) => {
            state.accessToken = action.payload;
        },
        logout: (state) => {
            state.user = null;
            state.accessToken = null;
            state.refreshToken = null;
            state.role = null;
            state.isAuthenticated = false;
        },
    },
});

export const { setCredentials, updateToken, logout } = authSlice.actions;

// Selectors
export const selectCurrentUser = (state: RootState) => state.auth.user;
export const selectAccessToken = (state: RootState) => state.auth.accessToken;
export const selectRefreshToken = (state: RootState) => state.auth.refreshToken;
export const selectUserRole = (state: RootState) => state.auth.role;
export const selectIsAuthenticated = (state: RootState) => state.auth.isAuthenticated;

export default authSlice.reducer;
