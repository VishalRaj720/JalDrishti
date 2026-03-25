import { useQuery } from '@tanstack/react-query';
import { useFetchAquifers } from './useFetchAquifers';
import { simulationsApi } from '@/api/simulationsApi';

export interface Alert {
    id: string;
    severity: 'error' | 'warning' | 'info' | 'success';
    title: string;
    message: string;
    entity: 'aquifer' | 'simulation' | 'district' | 'system';
    entityId: string;
}

export const useAlerts = () => {
    const { data: aquifers = [] } = useFetchAquifers();
    const { data: simulations = [] } = useQuery({
        queryKey: ['simulations', 'all'],
        queryFn: () => simulationsApi.getAll(),
        staleTime: 60 * 1000,
    });
    
    const alerts: Alert[] = [];
    
    // Alert 1: Missing critical data
    aquifers.forEach(aq => {
        if (aq.porosity == null || aq.hydraulic_conductivity == null) {
            alerts.push({
                id: `data-${aq.id}`,
                severity: 'warning',
                title: 'Incomplete Aquifer Data',
                message: `Aquifer "${aq.name}" is missing ${aq.porosity == null ? 'porosity' : 'hydraulic conductivity'}. Simulation accuracy will be reduced.`,
                entity: 'aquifer',
                entityId: aq.id,
            });
        }
    });
    
    // Alert 2: Simulation WHO limits
    simulations.forEach(sim => {
        const uranium = sim.estimated_concentration_spread?.uranium;
        if (uranium?.exceeds_limit) {
            alerts.push({
                id: `uranium-${sim.id}`,
                severity: 'error',
                title: 'WHO Uranium Limit Exceeded',
                message: `Simulation ${sim.id.substring(0,8)} shows uranium at ${uranium.max.toFixed(4)} mg/L (limit: 0.03).`,
                entity: 'simulation',
                entityId: sim.id,
            });
        }
    });
    
    // Alert 3: Uncertainty warning
    simulations.forEach(sim => {
        if (sim.status === 'completed' && (sim.uncertainty_estimate ?? 0) > 0.25) {
            alerts.push({
                id: `uncertainty-${sim.id}`,
                severity: 'warning',
                title: 'High Simulation Uncertainty',
                message: `Uncertainty at ${((sim.uncertainty_estimate ?? 0) * 100).toFixed(0)}%. Add hydraulic data to improve.`,
                entity: 'simulation',
                entityId: sim.id,
            });
        }
    });
    
    return alerts;
};
