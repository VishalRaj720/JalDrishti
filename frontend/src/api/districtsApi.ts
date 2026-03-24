import axiosInstance from './axiosInstance';
import type { District, DistrictCreate, DistrictUpdate, Block, BlockCreate, BlockUpdate } from '@/types/district';

// ── Districts ─────────────────────────────────────────────────────
export const districtsApi = {
    getAll: async (): Promise<District[]> => {
        const { data } = await axiosInstance.get<District[]>('/districts/');
        return data;
    },

    getById: async (id: string): Promise<District> => {
        const { data } = await axiosInstance.get<District>(`/districts/${id}`);
        return data;
    },

    create: async (payload: DistrictCreate): Promise<District> => {
        const { data } = await axiosInstance.post<District>('/districts/', payload);
        return data;
    },

    update: async (id: string, payload: DistrictUpdate): Promise<District> => {
        const { data } = await axiosInstance.put<District>(`/districts/${id}`, payload);
        return data;
    },

    delete: async (id: string): Promise<void> => {
        await axiosInstance.delete(`/districts/${id}`);
    },
};

// ── Blocks ────────────────────────────────────────────────────────
export const blocksApi = {
    getByDistrict: async (districtId: string): Promise<Block[]> => {
        const { data } = await axiosInstance.get<Block[]>(`/districts/${districtId}/blocks/`);
        return data;
    },

    getById: async (districtId: string, blockId: string): Promise<Block> => {
        const { data } = await axiosInstance.get<Block>(
            `/districts/${districtId}/blocks/${blockId}`
        );
        return data;
    },

    create: async (districtId: string, payload: BlockCreate): Promise<Block> => {
        const { data } = await axiosInstance.post<Block>(
            `/districts/${districtId}/blocks/`,
            payload
        );
        return data;
    },

    update: async (
        districtId: string,
        blockId: string,
        payload: BlockUpdate
    ): Promise<Block> => {
        const { data } = await axiosInstance.put<Block>(
            `/districts/${districtId}/blocks/${blockId}`,
            payload
        );
        return data;
    },

    delete: async (districtId: string, blockId: string): Promise<void> => {
        await axiosInstance.delete(`/districts/${districtId}/blocks/${blockId}`);
    },
};
