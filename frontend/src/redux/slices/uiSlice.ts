import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { RootState } from '../store';

interface FeatureFlags {
    enablePhysicsHybrid: boolean;
    enableMonteCarlo: boolean;
    enableDeckGL: boolean;
}

interface MapLayerVisibility {
    districts: boolean;
    blocks: boolean;
    aquifers: boolean;
    isr_points: boolean;
    plumes: boolean;
}

interface UIState {
    featureFlags: FeatureFlags;
    mapLayerVisibility: MapLayerVisibility;
    sidebarOpen: boolean;
}

const initialState: UIState = {
    featureFlags: {
        enablePhysicsHybrid: false,
        enableMonteCarlo: false,
        enableDeckGL: false,
    },
    mapLayerVisibility: {
        districts: true,
        blocks: true,
        aquifers: true,
        isr_points: true,
        plumes: true,
    },
    sidebarOpen: true,
};

const uiSlice = createSlice({
    name: 'ui',
    initialState,
    reducers: {
        toggleFeatureFlag: (state, action: PayloadAction<keyof FeatureFlags>) => {
            state.featureFlags[action.payload] = !state.featureFlags[action.payload];
        },
        setFeatureFlag: (
            state,
            action: PayloadAction<{ flag: keyof FeatureFlags; value: boolean }>
        ) => {
            state.featureFlags[action.payload.flag] = action.payload.value;
        },
        toggleLayerVisibility: (
            state,
            action: PayloadAction<keyof MapLayerVisibility>
        ) => {
            state.mapLayerVisibility[action.payload] =
                !state.mapLayerVisibility[action.payload];
        },
        setSidebarOpen: (state, action: PayloadAction<boolean>) => {
            state.sidebarOpen = action.payload;
        },
    },
});

export const {
    toggleFeatureFlag,
    setFeatureFlag,
    toggleLayerVisibility,
    setSidebarOpen,
} = uiSlice.actions;

// Selectors
export const selectFeatureFlags = (state: RootState) => state.ui.featureFlags;
export const selectMapLayerVisibility = (state: RootState) =>
    state.ui.mapLayerVisibility;
export const selectSidebarOpen = (state: RootState) => state.ui.sidebarOpen;

export default uiSlice.reducer;
