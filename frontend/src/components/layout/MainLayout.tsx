import { Outlet } from 'react-router-dom';
import { Box } from '@mui/material';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { MapProvider } from '@/contexts/MapContext';
import { useSimulationWebSocket } from '@/hooks/useSimulationWebSocket';
import { useSelector } from 'react-redux';
import { selectSidebarOpen } from '@/redux/slices/uiSlice';

const SIDEBAR_WIDTH = 240;

export const MainLayout: React.FC = () => {
    useSimulationWebSocket();  // Connect WS for the lifetime of the authenticated layout
    const sidebarOpen = useSelector(selectSidebarOpen);

    return (
        <MapProvider>
            <Box sx={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
                <Sidebar width={SIDEBAR_WIDTH} />
                <Box
                    component="main"
                    sx={{
                        flexGrow: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        ml: sidebarOpen ? `${SIDEBAR_WIDTH}px` : 0,
                        transition: 'margin 0.3s ease',
                        overflow: 'hidden',
                    }}
                >
                    <Header />
                    <Box sx={{ flexGrow: 1, overflow: 'auto', p: 3 }}>
                        <Outlet />
                    </Box>
                </Box>
            </Box>
        </MapProvider>
    );
};
