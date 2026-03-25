import { useEffect } from 'react';
import { BrowserRouter } from 'react-router-dom';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { useDispatch } from 'react-redux';
import { authApi } from './api/authApi';
import { setCredentials, setInitialized } from './redux/slices/authSlice';
import { AppRoutes } from './routes/AppRoutes';
import theme from './theme';

function App() {
    const dispatch = useDispatch();

    useEffect(() => {
        const initAuth = async () => {
            try {
                const tokens = await authApi.refresh();
                // Temporarily set token so getMe request is authenticated
                dispatch(setCredentials({ 
                    user: { id: '', username: '', email: '', role: 'viewer', created_at: '', updated_at: '' }, 
                    accessToken: tokens.access_token,
                    refreshToken: tokens.refresh_token
                }));
                const user = await authApi.getMe();
                dispatch(setCredentials({ user, accessToken: tokens.access_token, refreshToken: tokens.refresh_token }));
            } catch (err) {
                // Not authenticated or session expired
            } finally {
                dispatch(setInitialized());
            }
        };
        initAuth();
    }, [dispatch]);

    return (
        <BrowserRouter>
            <ThemeProvider theme={theme}>
                <CssBaseline />
                <AppRoutes />
            </ThemeProvider>
        </BrowserRouter>
    );
}

export default App;
