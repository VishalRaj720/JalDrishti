import axiosInstance from './axiosInstance';
import type { IsrPoint, IsrPointCreate, IsrPointUpdate } from '@/types/simulation';

export const isrApi = {
    getAll: async (): Promise<IsrPoint[]> => {
        const { data } = await axiosInstance.get<IsrPoint[]>('/isr-points/');
        return data;
    },

    getById: async (id: string): Promise<IsrPoint> => {
        const { data } = await axiosInstance.get<IsrPoint>(`/isr-points/${id}`);
        return data;
    },

    create: async (payload: IsrPointCreate): Promise<IsrPoint> => {
        const { data } = await axiosInstance.post<IsrPoint>('/isr-points/', payload);
        return data;
    },

    update: async (id: string, payload: IsrPointUpdate): Promise<IsrPoint> => {
        const { data } = await axiosInstance.put<IsrPoint>(`/isr-points/${id}`, payload);
        return data;
    },

    delete: async (id: string): Promise<void> => {
        await axiosInstance.delete(`/isr-points/${id}`);
    },

    runSimulation: async (
        isrId: string,
        params?: object
    ): Promise<{ job_id: string; simulation_id: string }> => {
        const { data } = await axiosInstance.post<{ job_id: string; simulation_id: string }>(
            `/simulations/${isrId}`,
            params ?? {}
        );
        return data;
    },
};
