import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { aquifersApi } from '@/api/aquifersApi';
import type { AquiferCreate, AquiferUpdate } from '@/types/aquifer';

export const AQUIFERS_QUERY_KEY = ['aquifers'] as const;

export const useFetchAquifers = (blockId?: string) => {
    return useQuery({
        queryKey: blockId ? [...AQUIFERS_QUERY_KEY, blockId] : AQUIFERS_QUERY_KEY,
        queryFn: () => aquifersApi.getAll(blockId ? { block_id: blockId } : undefined),
        staleTime: 5 * 60 * 1000,
    });
};

export const useCreateAquifer = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: AquiferCreate) => aquifersApi.create(payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: AQUIFERS_QUERY_KEY });
        },
    });
};

export const useUpdateAquifer = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: AquiferUpdate }) =>
            aquifersApi.update(id, payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: AQUIFERS_QUERY_KEY });
        },
    });
};

export const useDeleteAquifer = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => aquifersApi.delete(id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: AQUIFERS_QUERY_KEY });
        },
    });
};
