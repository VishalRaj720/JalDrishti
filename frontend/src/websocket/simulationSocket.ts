import { store } from '@/redux/store';
import { processSimulationEvent } from '@/redux/slices/simulationsSlice';
import type { SimulationCompleteEvent } from '@/types/simulation';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';

class SimulationSocketClient {
    private socket: WebSocket | null = null;
    private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    private maxRetries = 5;
    private retryCount = 0;
    private shouldReconnect = true;

    connect(): void {
        if (this.socket?.readyState === WebSocket.OPEN) return;

        const token = store.getState().auth.accessToken;
        const url = token
            ? `${WS_URL}/ws/simulations?token=${token}`
            : `${WS_URL}/ws/simulations`;

        this.socket = new WebSocket(url);

        this.socket.onopen = () => {
            console.info('[SimulationSocket] Connected');
            this.retryCount = 0;
        };

        this.socket.onmessage = (event: MessageEvent) => {
            try {
                const payload = JSON.parse(event.data as string) as {
                    type: string;
                    data: SimulationCompleteEvent;
                };
                if (payload.type === 'simulation_complete') {
                    store.dispatch(processSimulationEvent(payload.data));
                }
            } catch (err) {
                console.warn('[SimulationSocket] Failed to parse message:', err);
            }
        };

        this.socket.onerror = (err) => {
            console.error('[SimulationSocket] Error:', err);
        };

        this.socket.onclose = () => {
            console.info('[SimulationSocket] Disconnected');
            if (this.shouldReconnect && this.retryCount < this.maxRetries) {
                this.retryCount++;
                const delay = Math.min(1000 * 2 ** this.retryCount, 30_000);
                console.info(`[SimulationSocket] Reconnecting in ${delay}ms…`);
                this.reconnectTimer = setTimeout(() => this.connect(), delay);
            }
        };
    }

    disconnect(): void {
        this.shouldReconnect = false;
        if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
        this.socket?.close();
        this.socket = null;
    }

    send(data: object): void {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        }
    }
}

// Singleton instance
export const simulationSocket = new SimulationSocketClient();
