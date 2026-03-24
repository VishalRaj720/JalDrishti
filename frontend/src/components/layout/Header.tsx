import { AppBar, Toolbar, Typography, IconButton, Avatar, Tooltip, Box, Chip } from '@mui/material';
import { LogoutOutlined, MenuOutlined } from '@mui/icons-material';
import { useDispatch } from 'react-redux';
import { setSidebarOpen, selectSidebarOpen } from '@/redux/slices/uiSlice';
import { useSelector } from 'react-redux';
import { useAuth } from '@/hooks/useAuth';
import { useNavigate } from 'react-router-dom';

const ROLE_COLORS: Record<string, 'error' | 'warning' | 'info'> = {
    admin: 'error',
    analyst: 'warning',
    viewer: 'info',
};

export const Header: React.FC = () => {
    const dispatch = useDispatch();
    const sidebarOpen = useSelector(selectSidebarOpen);
    const { user, role, logoutUser } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logoutUser();
        navigate('/login');
    };

    return (
        <AppBar
            position="static"
            elevation={0}
            sx={{
                bgcolor: 'background.paper',
                borderBottom: '1px solid',
                borderColor: 'divider',
                color: 'text.primary',
            }}
        >
            <Toolbar>
                <IconButton
                    edge="start"
                    onClick={() => dispatch(setSidebarOpen(!sidebarOpen))}
                    sx={{ mr: 2, color: 'text.secondary' }}
                    aria-label="Toggle sidebar"
                >
                    <MenuOutlined />
                </IconButton>

                <Box sx={{ flexGrow: 1 }} />

                {role && (
                    <Chip
                        label={role.toUpperCase()}
                        size="small"
                        color={ROLE_COLORS[role] ?? 'default'}
                        sx={{ mr: 2, fontWeight: 700, fontSize: '0.65rem', letterSpacing: '0.08em' }}
                    />
                )}

                <Tooltip title={user?.email ?? ''}>
                    <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.dark', fontSize: '0.875rem', mr: 1, cursor: 'pointer' }}>
                        {user?.username?.[0]?.toUpperCase() ?? 'U'}
                    </Avatar>
                </Tooltip>

                <Typography variant="body2" color="text.secondary" sx={{ mr: 2 }}>
                    {user?.username}
                </Typography>

                <Tooltip title="Logout">
                    <IconButton onClick={handleLogout} sx={{ color: 'text.secondary' }} aria-label="Logout">
                        <LogoutOutlined fontSize="small" />
                    </IconButton>
                </Tooltip>
            </Toolbar>
        </AppBar>
    );
};
