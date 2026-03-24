import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { districtsApi } from '@/api/districtsApi';
import type { DistrictCreate, DistrictUpdate } from '@/types/district';

export const DISTRICTS_QUERY_KEY = ['districts'] as const;

export const useFetchDistricts = () => {
    return useQuery({
        queryKey: DISTRICTS_QUERY_KEY,
        queryFn: districtsApi.getAll,
        staleTime: 5 * 60 * 1000,
    });
};

export const useCreateDistrict = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (payload: DistrictCreate) => districtsApi.create(payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: DISTRICTS_QUERY_KEY });
        },
    });
};

export const useUpdateDistrict = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ id, payload }: { id: string; payload: DistrictUpdate }) =>
            districtsApi.update(id, payload),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: DISTRICTS_QUERY_KEY });
        },
    });
};

export const useDeleteDistrict = () => {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (id: string) => districtsApi.delete(id),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: DISTRICTS_QUERY_KEY });
        },
    });
};
