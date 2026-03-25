import axiosInstance from './axiosInstance';
import type { Simulation } from '@/types/simulation';

export const simulationsApi = {
    getAll: async (): Promise<Simulation[]> => {
        const { data } = await axiosInstance.get<Simulation[]>('/simulations/');
        return data;
    },

    getById: async (id: string): Promise<Simulation> => {
        const { data } = await axiosInstance.get<Simulation>(`/simulations/${id}`);
        return data;
    },

    getByIsrPoint: async (isrId: string): Promise<Simulation[]> => {
        const { data } = await axiosInstance.get<Simulation[]>(
            `/simulations/?isr_point_id=${isrId}`
        );
        return data;
    },

    run: async (isrId: string): Promise<Simulation> => {
        const { data } = await axiosInstance.post<Simulation>('/simulations/', { isr_point_id: isrId });
        return data;
    },
};
