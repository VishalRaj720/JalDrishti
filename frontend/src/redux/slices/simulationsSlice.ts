import { createSlice, createAsyncThunk, type PayloadAction } from '@reduxjs/toolkit';
import type { Simulation, SimulationCompleteEvent } from '@/types/simulation';
import type { RootState } from '../store';

interface SimulationsState {
    results: Record<string, Simulation>;
    activeId: string | null;
    loading: boolean;
}

const initialState: SimulationsState = {
    results: {},
    activeId: null,
    loading: false,
};

/**
 * Thunk called by WebSocket on 'simulation_complete' event.
 * Merges the result into the store.
 */
export const processSimulationEvent = createAsyncThunk(
    'simulations/processEvent',
    async (event: SimulationCompleteEvent, { dispatch }) => {
        dispatch(simulationsSlice.actions.upsertSimulation({
            ...event.result,
            id: event.simulation_id,
            status: event.status,
        } as Simulation));
    }
);

const simulationsSlice = createSlice({
    name: 'simulations',
    initialState,
    reducers: {
        upsertSimulation: (state, action: PayloadAction<Simulation>) => {
            state.results[action.payload.id] = action.payload;
        },
        setActiveSimulation: (state, action: PayloadAction<string | null>) => {
            state.activeId = action.payload;
        },
        clearSimulations: (state) => {
            state.results = {};
            state.activeId = null;
        },
    },
    extraReducers: (builder) => {
        builder
            .addCase(processSimulationEvent.pending, (state) => {
                state.loading = true;
            })
            .addCase(processSimulationEvent.fulfilled, (state) => {
                state.loading = false;
            });
    },
});

export const { upsertSimulation, setActiveSimulation, clearSimulations } =
    simulationsSlice.actions;

// Selectors
export const selectAllSimulations = (state: RootState) =>
    Object.values(state.simulations.results);

export const selectSimulationById = (id: string) => (state: RootState) =>
    state.simulations.results[id];

export const selectPlumeGeometryBySimulationId =
    (id: string) => (state: RootState) =>
        state.simulations.results[id]?.estimated_concentration_spread?.geometry ?? null;

export const selectUncertaintyById = (id: string) => (state: RootState) =>
    state.simulations.results[id]?.uncertainty_estimate ?? null;

export default simulationsSlice.reducer;
