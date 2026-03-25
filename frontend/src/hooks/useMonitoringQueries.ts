import { useQuery } from '@tanstack/react-query';
import axiosInstance from '@/api/axiosInstance';
import { simulationsApi } from '@/api/simulationsApi';

export const useMonitoringData = (aquiferId: string | undefined) => {
    return useQuery({
        queryKey: ['monitoring', aquiferId],
        queryFn: () => axiosInstance.get(`/aquifers/${aquiferId}/monitoring`).then(r => r.data),
        staleTime: 60 * 1000,
        enabled: !!aquiferId,
    });
};

export const useSimulationsByIsr = (isrId: string | undefined) => {
    return useQuery({
        queryKey: ['simulations', 'isr', isrId],
        queryFn: () => simulationsApi.getByIsrPoint(isrId!),
        staleTime: 30 * 1000,
        enabled: !!isrId,
        refetchInterval: (query) => {
            const hasRunning = query.state.data?.some(s => s.status === 'running' || s.status === 'pending');
            return hasRunning ? 5000 : false;
        },
    });
};
