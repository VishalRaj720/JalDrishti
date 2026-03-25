import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { districtsApi, blocksApi } from '@/api/districtsApi';
import type { DistrictCreate, DistrictUpdate } from '@/types/district';

export const DISTRICTS_QUERY_KEY = ['districts'] as const;

export const useFetchDistricts = (skip: number = 0, limit: number = 100) => {
    return useQuery({
        queryKey: [...DISTRICTS_QUERY_KEY, skip, limit],
        queryFn: () => districtsApi.getAll(skip, limit),
        staleTime: 5 * 60 * 1000,
    });
};

export const useFetchDistrictDetail = (districtId: string | null) => {
    return useQuery({
        queryKey: ['districts', districtId, 'detail'],
        queryFn: async () => {
            const [detail, blocks] = await Promise.all([
                districtsApi.getById(districtId!),
                blocksApi.getByDistrict(districtId!)
            ]);
            return { ...detail, blocks };
        },
        enabled: !!districtId,
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
