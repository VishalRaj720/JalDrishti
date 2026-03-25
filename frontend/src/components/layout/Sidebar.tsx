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
    { label: 'Blocks', path: '/blocks', icon: <MapOutlined /> },
    { label: 'Aquifers', path: '/aquifers', icon: <WaterOutlined /> },
    { label: 'ISR Points', path: '/isr-points', icon: <ScienceOutlined />, analystOnly: true },
    { label: 'Simulations', path: '/simulations', icon: <LocationOnOutlined /> },
];

interface Props { open: boolean; }

export const Sidebar: React.FC<Props> = ({ open }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const { isAnalystOrAdmin } = useRBAC();

    const filteredItems = NAV_ITEMS.filter(
        (item) => !item.analystOnly || isAnalystOrAdmin
    );

    const SIDEBAR_WIDTH = 240;
    const COLLAPSED_WIDTH = 64;

    return (
        <Drawer 
            variant="permanent" 
            sx={{ 
                width: open ? SIDEBAR_WIDTH : COLLAPSED_WIDTH, 
                flexShrink: 0, 
                whiteSpace: 'nowrap',
                transition: 'width 0.2s ease',
                '& .MuiDrawer-paper': { 
                    width: open ? SIDEBAR_WIDTH : COLLAPSED_WIDTH, 
                    boxSizing: 'border-box',
                    overflowX: 'hidden',
                    transition: 'width 0.2s ease',
                } 
            }}
        >
            {/* Brand */}
            <Box sx={{ px: open ? 2.5 : 1, py: 3, display: 'flex', justifyContent: open ? 'flex-start' : 'center', transition: 'all 0.2s' }}>
                <Typography variant="h6" fontWeight={700} color="primary.main" letterSpacing="-0.02em" sx={{ overflow: 'hidden', textOverflow: 'clip' }}>
                    {open ? '💧 JalDrishti' : '💧'}
                </Typography>
            </Box>

            <Divider />

            <List sx={{ mt: 1, px: 1 }}>
                {filteredItems.map((item) => {
                    const active = location.pathname.startsWith(item.path);
                    return (
                        <ListItem key={item.path} disablePadding sx={{ mb: 0.5, px: open ? 0 : 0.5 }}>
                            <ListItemButton
                                onClick={() => navigate(item.path)}
                                sx={{
                                    borderRadius: 2,
                                    justifyContent: open ? 'initial' : 'center',
                                    px: open ? 2 : 1.5,
                                    color: active ? 'primary.main' : 'text.secondary',
                                    bgcolor: active ? 'rgba(56,189,248,0.08)' : 'transparent',
                                    '&:hover': {
                                        bgcolor: 'rgba(56,189,248,0.06)',
                                        color: 'primary.light',
                                    },
                                }}
                            >
                                <ListItemIcon sx={{ color: 'inherit', minWidth: 40, mr: open ? 0 : 'auto', justifyContent: 'center' }}>
                                    {item.icon}
                                </ListItemIcon>
                                {open && (
                                    <>
                                        <ListItemText
                                            primary={item.label}
                                            primaryTypographyProps={{ fontSize: '0.875rem', fontWeight: active ? 600 : 400 }}
                                        />
                                        {item.analystOnly && (
                                            <Chip label="Analyst" size="small" color="secondary" sx={{ height: 18, fontSize: 10 }} />
                                        )}
                                    </>
                                )}
                            </ListItemButton>
                        </ListItem>
                    );
                })}
            </List>

            {/* Version badge */}
            <Box sx={{ mt: 'auto', p: 2, textAlign: open ? 'left' : 'center', whiteSpace: 'nowrap' }}>
                <Typography variant="caption" color="text.disabled" sx={{ display: open ? 'block' : 'none' }}>
                    v1.0.0 · JalDrishti
                </Typography>
                {!open && <Typography variant="caption" color="text.disabled">v1</Typography>}
            </Box>
        </Drawer>
    );
};
