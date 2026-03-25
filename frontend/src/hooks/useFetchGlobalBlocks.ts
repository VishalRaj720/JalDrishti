import { useQuery } from '@tanstack/react-query';
import { globalBlocksApi } from '@/api/globalBlocksApi';
import { blocksApi } from '@/api/districtsApi';
import { aquifersApi } from '@/api/aquifersApi';

export const BLOCKS_QUERY_KEY = ['blocks', 'global'] as const;

export const useFetchGlobalBlocks = (skip: number = 0, limit: number = 100) => {
    return useQuery({
        queryKey: [...BLOCKS_QUERY_KEY, skip, limit],
        queryFn: () => globalBlocksApi.getAll(skip, limit),
        staleTime: 5 * 60 * 1000,
    });
};

export const useFetchBlockDetail = (districtId: string | null, blockId: string | null) => {
    return useQuery({
        queryKey: ['blocks', blockId, 'detail'],
        queryFn: async () => {
            const [detail, aquifers] = await Promise.all([
                blocksApi.getById(districtId!, blockId!),
                aquifersApi.getAll({ block_id: blockId! })
            ]);
            return { ...detail, aquifers };
        },
        enabled: !!districtId && !!blockId,
        staleTime: 5 * 60 * 1000,
    });
};
