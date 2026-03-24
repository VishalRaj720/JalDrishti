import {
    Drawer,
    List,
    ListItem,
    ListItemButton,
    ListItemIcon,
    ListItemText,
    Box,
    Typography,
    Divider,
    Chip,
} from '@mui/material';
import {
    DashboardOutlined,
    MapOutlined,
    WaterOutlined,
    ScienceOutlined,
    LocationOnOutlined,
} from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useRBAC } from '@/hooks/useRBAC';

const NAV_ITEMS = [
    { label: 'Dashboard', path: '/dashboard', icon: <DashboardOutlined /> },
    { label: 'Districts', path: '/districts', icon: <MapOutlined /> },
    { label: 'Aquifers', path: '/aquifers', icon: <WaterOutlined /> },
    { label: 'ISR Points', path: '/isr-points', icon: <ScienceOutlined />, analystOnly: true },
    { label: 'Simulations', path: '/simulations', icon: <LocationOnOutlined /> },
];

interface Props { width: number; }

export const Sidebar: React.FC<Props> = ({ width }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { isAnalystOrAdmin } = useRBAC();

    const filteredItems = NAV_ITEMS.filter(
        (item) => !item.analystOnly || isAnalystOrAdmin
    );

    return (
        <Drawer variant="permanent" sx={{ width, flexShrink: 0, '& .MuiDrawer-paper': { width, boxSizing: 'border-box' } }}>
            {/* Brand */}
            <Box sx={{ px: 2.5, py: 3 }}>
                <Typography variant="h6" fontWeight={700} color="primary.main" letterSpacing="-0.02em">
                    💧 JalDrishti
                </Typography>
                <Typography variant="caption" color="text.secondary">
                    Groundwater Intelligence
                </Typography>
            </Box>

            <Divider />

            <List sx={{ mt: 1, px: 1 }}>
                {filteredItems.map((item) => {
                    const active = location.pathname.startsWith(item.path);
                    return (
                        <ListItem key={item.path} disablePadding sx={{ mb: 0.5 }}>
                            <ListItemButton
                                onClick={() => navigate(item.path)}
                                sx={{
                                    borderRadius: 2,
                                    color: active ? 'primary.main' : 'text.secondary',
                                    bgcolor: active ? 'rgba(56,189,248,0.08)' : 'transparent',
                                    '&:hover': {
                                        bgcolor: 'rgba(56,189,248,0.06)',
                                        color: 'primary.light',
                                    },
                                }}
                            >
                                <ListItemIcon sx={{ color: 'inherit', minWidth: 40 }}>
                                    {item.icon}
                                </ListItemIcon>
                                <ListItemText
                                    primary={item.label}
                                    primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: active ? 600 : 400 }}
                                />
                                {item.analystOnly && (
                                    <Chip label="Analyst" size="small" color="secondary" sx={{ height: 18, fontSize: 10 }} />
                                )}
                            </ListItemButton>
                        </ListItem>
                    );
                })}
            </List>

            {/* Version badge */}
            <Box sx={{ mt: 'auto', p: 2 }}>
                <Typography variant="caption" color="text.disabled">
                    v1.0.0 · JalDrishti
                </Typography>
            </Box>
        </Drawer>
    );
};
