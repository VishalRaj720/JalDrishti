import React from 'react';
import { Card, CardContent, Typography, LinearProgress, Box, Chip } from '@mui/material';
import { useFetchAquifers } from '@/hooks/useFetchAquifers';

const REQUIRED_FIELDS = [
    { key: 'porosity', label: 'Porosity', impact: 'High' },
    { key: 'hydraulic_conductivity', label: 'Hyd. Conductivity', impact: 'High' },
    { key: 'transmissivity', label: 'Transmissivity', impact: 'Medium' },
    { key: 'dtw_decadal_avg', label: 'Depth to Water', impact: 'Medium' },
];

export const AquiferDataCompletenessPanel: React.FC = () => {
    const { data: aquifers = [] } = useFetchAquifers();
    
    const incompleteAquifers = aquifers.filter(aq =>
        REQUIRED_FIELDS.some(f => (aq as any)[f.key] == null)
    );
    
    const total = Math.max(aquifers.length, 1);
    const completeCount = aquifers.length - incompleteAquifers.length;
    const pct = (completeCount / total) * 100;

    return (
        <Card sx={{ height: '100%' }}>
            <CardContent>
                <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                    Data Completeness
                </Typography>
                <Typography variant="body2" color="text.secondary">
                    {completeCount} / {aquifers.length} Aquifers Fully Profiled
                </Typography>
                
                <LinearProgress
                    variant="determinate"
                    value={pct}
                    color={pct > 80 ? 'success' : pct > 50 ? 'warning' : 'error'}
                    sx={{ my: 2, height: 8, borderRadius: 4 }}
                />
                
                {incompleteAquifers.slice(0, 5).map(aq => (
                    <Box key={aq.id} display="flex" justifyContent="space-between" py={0.75} borderBottom="1px solid" borderColor="divider">
                        <Typography variant="body2" noWrap sx={{ maxWidth: '40%' }}>
                            {aq.name}
                        </Typography>
                        <Box display="flex" gap={0.5} flexWrap="wrap" justifyContent="flex-end" sx={{ maxWidth: '60%' }}>
                            {REQUIRED_FIELDS
                                .filter(f => (aq as any)[f.key] == null)
                                .map(f => (
                                    <Chip key={f.key} label={f.label} size="small" color="warning" sx={{ fontSize: '0.65rem', height: 20 }} />
                                ))}
                        </Box>
                    </Box>
                ))}
            </CardContent>
        </Card>
    );
};
