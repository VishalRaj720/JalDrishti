import axiosInstance from './axiosInstance';
import type { Aquifer, AquiferCreate, AquiferUpdate } from '@/types/aquifer';

export const aquifersApi = {
    getAll: async (params?: { block_id?: string; skip?: number; limit?: number }): Promise<Aquifer[]> => {
        const { data } = await axiosInstance.get<Aquifer[]>('/aquifers', { params });
        return data;
    },

    getById: async (id: string): Promise<Aquifer> => {
        const { data } = await axiosInstance.get<Aquifer>(`/aquifers/${id}`);
        return data;
    },

    create: async (payload: AquiferCreate): Promise<Aquifer> => {
        const { data } = await axiosInstance.post<Aquifer>('/aquifers', payload);
        return data;
    },

    update: async (id: string, payload: AquiferUpdate): Promise<Aquifer> => {
        const { data } = await axiosInstance.put<Aquifer>(`/aquifers/${id}`, payload);
        return data;
    },

    delete: async (id: string): Promise<void> => {
        await axiosInstance.delete(`/aquifers/${id}`);
    },
};
