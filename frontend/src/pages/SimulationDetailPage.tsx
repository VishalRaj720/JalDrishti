import { lazy, Suspense } from 'react';
import { useParams } from 'react-router-dom';
import {
    Box, Typography, Grid, Card, CardContent, Chip,
    Alert, LinearProgress, Divider, Tooltip,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { simulationsApi } from '@/api/simulationsApi';
import { useSelector } from 'react-redux';
import { SimulationResultCard } from '@/components/simulations/SimulationResultCard';
import { selectPlumeGeometryBySimulationId, selectUncertaintyById } from '@/redux/slices/simulationsSlice';
import { SIMULATION_STATUS_LABELS } from '@/utils/constants';
import LoadingSpinner from '@/components/common/LoadingSpinner';

const MapView = lazy(() => import('@/components/geospatial/MapView'));
const LayerControls = lazy(() => import('@/components/geospatial/LayerControls').then(m => ({ default: m.LayerControls })));

const STATUS_COLORS = {
    pending: 'default',
    running: 'warning',
    completed: 'success',
    failed: 'error',
} as const;

const SimulationDetailPage: React.FC = () => {
    const { id } = useParams<{ id: string }>();

    const { data: sim, isLoading, isError } = useQuery({
        queryKey: ['simulations', id],
        queryFn: () => simulationsApi.getById(id!),
        enabled: !!id,
        refetchInterval: (queryOrData: any) => {
            const data = queryOrData?.state?.data ?? queryOrData;
            return data?.status === 'running' || data?.status === 'pending' ? 3000 : false;
        },
    });

    // Subscribe to real-time updates from WebSocket via Redux
    const plumeGeom = useSelector(selectPlumeGeometryBySimulationId(id ?? ''));
    const uncertainty = useSelector(selectUncertaintyById(id ?? ''));

    const effectiveUncertainty = uncertainty ?? sim?.uncertainty_estimate;
    const highUncertainty = effectiveUncertainty != null && effectiveUncertainty > 0.2;

    // (Concentration chart data handled inside SimulationResultCard)

    if (isLoading) return <LoadingSpinner />;
    if (isError || !sim) {
        return <Alert severity="error">Could not load simulation data.</Alert>;
    }

    const vulnerability = sim.vulnerability_assessment;

    return (
        <Box>
            <Box display="flex" alignItems="center" gap={2} mb={3}>
                <Typography variant="h5" fontWeight={700}>Simulation Result</Typography>
                <Chip
                    label={SIMULATION_STATUS_LABELS[sim.status] ?? sim.status}
                    color={STATUS_COLORS[sim.status] ?? 'default'}
                    size="small"
                />
                {sim.model_version && (
                    <Chip label={`Model: ${sim.model_version}`} size="small" variant="outlined" />
                )}
            </Box>

            {sim.status === 'running' && <LinearProgress sx={{ mb: 2 }} />}

            {sim.status === 'failed' && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    {sim.error_message ?? 'Simulation failed due to an unknown error.'}
                </Alert>
            )}

            {highUncertainty && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                    High uncertainty ({((effectiveUncertainty ?? 0) * 100).toFixed(0)}%). Results may be imprecise — consider ingesting piezometric or hydraulic conductivity data.
                </Alert>
            )}

            <Grid container spacing={2} mb={2}>
                {/* Key metrics */}
                {[
                    { label: 'Risk Score', value: vulnerability?.risk_score?.toFixed(2) ?? '—' },
                    { label: 'Risk Level', value: vulnerability?.risk_level ?? '—' },
                    { label: 'Affected Area', value: sim.affected_area != null ? `${(sim.affected_area / 1e6).toFixed(2)} km²` : '—' },
                    { label: 'Uncertainty', value: effectiveUncertainty != null ? `${(effectiveUncertainty * 100).toFixed(1)}%` : '—' },
                ].map(({ label, value }) => (
                    <Grid item xs={6} sm={3} key={label}>
                        <Card>
                            <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                                <Typography variant="caption" color="text.secondary">{label}</Typography>
                                <Typography variant="h6" fontWeight={700}>{value}</Typography>
                            </CardContent>
                        </Card>
                    </Grid>
                ))}
            </Grid>

            <Grid container spacing={2}>
                {/* Map */}
                <Grid item xs={12} md={8}>
                    <Suspense fallback={<LoadingSpinner />}>
                        <MapView height={400} />
                    </Suspense>
                </Grid>
                <Grid item xs={12} md={4}>
                    <Suspense fallback={null}>
                        <LayerControls />
                    </Suspense>

                    {sim.suggested_recovery && (
                        <Card sx={{ mt: 2 }}>
                            <CardContent>
                                <Typography variant="subtitle2" color="secondary.main" mb={1}>
                                    🔧 Suggested Recovery
                                </Typography>
                                <Typography variant="body2">{sim.suggested_recovery}</Typography>
                            </CardContent>
                        </Card>
                    )}
                </Grid>

                {/* Concentration spread chart */}
                <Grid item xs={12}>
                    <SimulationResultCard simulation={sim as any} />
                </Grid>

                {/* Audit */}
                <Grid item xs={12}>
                    <Typography variant="caption" color="text.disabled">
                        Simulation ID: {sim.id} · Run at: {new Date(sim.simulation_date).toLocaleString()}
                        {sim.run_by ? ` · by ${sim.run_by}` : ''}
                    </Typography>
                </Grid>
            </Grid>
        </Box>
    );
};

export default SimulationDetailPage;
