import { configureStore } from '@reduxjs/toolkit';
import authReducer from './slices/authSlice';
import simulationsReducer from './slices/simulationsSlice';
import uiReducer from './slices/uiSlice';

export const store = configureStore({
    reducer: {
        auth: authReducer,
        simulations: simulationsReducer,
        ui: uiReducer,
    },
    devTools: import.meta.env.DEV,
});

// Inferred types
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
