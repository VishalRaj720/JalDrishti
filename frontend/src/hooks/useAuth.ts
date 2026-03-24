import { useSelector, useDispatch } from 'react-redux';
import {
    selectCurrentUser,
    selectAccessToken,
    selectUserRole,
    selectIsAuthenticated,
    setCredentials,
    logout,
} from '@/redux/slices/authSlice';
import type { AppDispatch } from '@/redux/store';
import { authApi } from '@/api/authApi';

export const useAuth = () => {
    const dispatch = useDispatch<AppDispatch>();
    const user = useSelector(selectCurrentUser);
    const accessToken = useSelector(selectAccessToken);
    const role = useSelector(selectUserRole);
    const isAuthenticated = useSelector(selectIsAuthenticated);

    const login = async (username: string, password: string) => {
        const tokens = await authApi.login({ username, password });
        // Temporarily set token so getMe request is authenticated
        dispatch(setCredentials({
            user: {
                id: '', username, email: username, role: 'viewer',
                created_at: '', updated_at: '',
            },
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
        }));
        const me = await authApi.getMe();
        dispatch(setCredentials({ user: me, accessToken: tokens.access_token, refreshToken: tokens.refresh_token }));
        return me;
    };

    const logoutUser = async () => {
        try { await authApi.logout(); } catch (_) { /* ignore */ }
        dispatch(logout());
    };

    return { user, accessToken, role, isAuthenticated, login, logoutUser };
};
