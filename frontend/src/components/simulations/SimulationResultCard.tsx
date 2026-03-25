import React from 'react';
import { Card, CardContent, Typography, Box, Chip } from '@mui/material';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import type { Simulation } from '@/types/simulation';

interface Props {
    simulation: Simulation;
}

export const SimulationResultCard: React.FC<Props> = ({ simulation }) => {
    const spread = simulation.estimated_concentration_spread;
    if (!spread || simulation.status !== 'completed') return null;

    const uranium = spread.uranium;
    // Map time steps to concentrations for chart
    const chartData = spread.time_steps?.map((time: number, index: number) => ({
        time,
        concentration: spread.concentrations?.[index] ?? 0,
    })) ?? [];

    return (
        <Card sx={{ mt: 3 }}>
            <CardContent>
                <Typography variant="h6" fontWeight={700} mb={2}>
                    Uranium Plume Risk Assessment
                </Typography>
                <Box display="flex" gap={2} mb={3} flexWrap="wrap">
                    <Box p={2} bgcolor="background.default" borderRadius={2} flex={1} minWidth={150}>
                        <Typography variant="caption" color="text.secondary">Area Affected</Typography>
                        <Typography variant="h5" fontWeight={600}>
                            {simulation.affected_area ? `${(simulation.affected_area / 1e6).toFixed(2)} km²` : '—'}
                        </Typography>
                    </Box>
                    <Box p={2} bgcolor="background.default" borderRadius={2} flex={1} minWidth={150}>
                        <Typography variant="caption" color="text.secondary">Max Uranium</Typography>
                        <Typography variant="h5" fontWeight={600} color={uranium?.exceeds_limit ? 'error.main' : 'text.primary'}>
                            {uranium?.max?.toFixed(4) ?? '—'} <Typography component="span" variant="body2">{uranium?.unit ?? 'mg/L'}</Typography>
                        </Typography>
                    </Box>
                </Box>
                
                {uranium?.exceeds_limit && (
                    <Box mb={3}>
                        <Chip label="WHO Limit Exceeded" color="error" size="small" sx={{ mb: 1, fontWeight: 700 }} />
                        <Typography variant="body2" color="error.light">
                            Uranium concentration exceeds the WHO safe drinking water limit of {uranium.who_limit} mg/L.
                        </Typography>
                    </Box>
                )}

                {chartData.length > 0 && (
                    <Box height={280}>
                        <Typography variant="subtitle2" mb={1} color="text.secondary">Concentration Over Time (Days)</Typography>
                        <ResponsiveContainer width="100%" height="80%">
                            <AreaChart data={chartData} margin={{ top: 20, right: 30, left: 0, bottom: 0 }}>
                                <defs>
                                    <linearGradient id="colorU" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor={uranium?.exceeds_limit ? "#ef4444" : "#f97316"} stopOpacity={0.8}/>
                                        <stop offset="95%" stopColor={uranium?.exceeds_limit ? "#ef4444" : "#f97316"} stopOpacity={0}/>
                                    </linearGradient>
                                </defs>
                                <XAxis dataKey="time" type="number" tick={{ fontSize: 12, fill: '#94a3b8' }} domain={['dataMin', 'dataMax']} />
                                <YAxis tick={{ fontSize: 12, fill: '#94a3b8' }} />
                                <Tooltip contentStyle={{ background: '#1e293b', border: 'none', borderRadius: 8 }} />
                                {uranium?.who_limit && (
                                    <ReferenceLine y={uranium.who_limit} stroke="#ef4444" strokeDasharray="3 3" label={{ position: 'insideTopLeft', value: 'WHO Limit', fill: '#ef4444', fontSize: 10 }} />
                                )}
                                <Area type="monotone" dataKey="concentration" stroke={uranium?.exceeds_limit ? "#ef4444" : "#f97316"} fillOpacity={1} fill="url(#colorU)" />
                            </AreaChart>
                        </ResponsiveContainer>
                    </Box>
                )}

                {simulation.suggested_recovery && (
                     <Box mt={3} p={2} border="1px solid" borderColor="divider" borderRadius={2}>
                        <Typography variant="subtitle2" color="success.main" mb={0.5}>Recovery Recommendation</Typography>
                        <Typography variant="body2">{simulation.suggested_recovery}</Typography>
                     </Box>
                )}
            </CardContent>
        </Card>
    );
};
