import axiosInstance from './axiosInstance';
import type { Block } from '@/types/district';

export const globalBlocksApi = {
    getAll: async (skip: number = 0, limit: number = 100): Promise<Block[]> => {
        const { data } = await axiosInstance.get<Block[]>('/blocks', { params: { skip, limit } });
        return data;
    },
};
