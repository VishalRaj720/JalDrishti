import type { AquiferType } from '@/types/aquifer';

export const AQUIFER_TYPES: { value: AquiferType; label: string }[] = [
    { value: 'unconfined', label: 'Unconfined' },
    { value: 'confined', label: 'Confined' },
    { value: 'semi_confined', label: 'Semi-Confined' },
    { value: 'perched', label: 'Perched' },
];

export const SIMULATION_STATUS_LABELS: Record<string, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
};
