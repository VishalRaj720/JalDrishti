import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { isrApi } from '@/api/isrApi';
import type { IsrPointCreate, IsrPointUpdate } from '@/types/simulation';

export const ISR_QUERY_KEY = ['isr-points'] as const;

export const useFetchIsrPoints = () => {
    return useQuery({
        queryKey: ISR_QUERY_KEY,
        queryFn: isrApi.getAll,
        staleTime: 3 * 60 * 1000,
    });
};

export const useCreateIsrPoint = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: IsrPointCreate) => isrApi.create(payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ISR_QUERY_KEY });
        },
    });
};

export const useUpdateIsrPoint = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: IsrPointUpdate }) =>
            isrApi.update(id, payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ISR_QUERY_KEY });
        },
    });
};

export const useDeleteIsrPoint = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => isrApi.delete(id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ISR_QUERY_KEY });
        },
    });
};

export const useRunSimulation = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ isrId, params }: { isrId: string; params?: object }) =>
            isrApi.runSimulation(isrId, params),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['simulations'] });
        },
    });
};
