import { useEffect } from 'react';
import { simulationSocket } from '@/websocket/simulationSocket';
import { useSelector } from 'react-redux';
import { selectIsAuthenticated } from '@/redux/slices/authSlice';

/**
 * Manages the lifecycle of the simulation WebSocket connection.
 * Connect when authenticated, disconnect on cleanup.
 * Use this hook once in a top-level authenticated layout.
 */
export const useSimulationWebSocket = () => {
    const isAuthenticated = useSelector(selectIsAuthenticated);

    useEffect(() => {
        if (!isAuthenticated) return;

        simulationSocket.connect();

        return () => {
            simulationSocket.disconnect();
        };
    }, [isAuthenticated]);
};
