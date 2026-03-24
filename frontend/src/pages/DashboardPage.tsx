import React, { lazy } from 'react';
import {
    Box, Grid, Typography, Card, CardContent, Chip,
    LinearProgress,
} from '@mui/material';
import {
    WaterOutlined, MapOutlined, ScienceOutlined, AssessmentOutlined,
} from '@mui/icons-material';
import {
    ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from 'recharts';
import { useFetchDistricts } from '@/hooks/useFetchDistricts';
import { useFetchAquifers } from '@/hooks/useFetchAquifers';
import { useFetchIsrPoints } from '@/hooks/useFetchIsrPoints';
import { useAuth } from '@/hooks/useAuth';
import { vulnerabilityColor } from '@/utils/geoUtils';

const DashboardPage: React.FC = () => {
    const { user } = useAuth();
    const { data: districts = [] } = useFetchDistricts();
    const { data: aquifers = [] } = useFetchAquifers();
    const { data: isrPoints = [] } = useFetchIsrPoints();

    // Vulnerability distribution for chart
    const vulnData = districts.map((d) => ({
        name: d.name.substring(0, 10),
        index: d.vulnerability_index ?? 0,
    }));

    const stats = [
        { label: 'Districts', value: districts.length, icon: <MapOutlined />, color: 'primary.main' },
        { label: 'Aquifers', value: aquifers.length, icon: <WaterOutlined />, color: 'secondary.main' },
        { label: 'ISR Points', value: isrPoints.length, icon: <ScienceOutlined />, color: 'warning.main' },
        {
            label: 'Avg Vulnerability',
            value: districts.length
                ? (districts.reduce((a, d) => a + (d.vulnerability_index ?? 0), 0) / districts.length).toFixed(2)
                : '—',
            icon: <AssessmentOutlined />,
            color: 'error.main',
        },
    ];

    return (
        <Box>
            <Typography variant="h5" fontWeight={700} mb={0.5}>
                Dashboard
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
                Welcome back, <strong>{user?.username}</strong>
            </Typography>

            {/* KPI Cards */}
            <Grid container spacing={2} mb={3}>
                {stats.map((stat) => (
                    <Grid item xs={12} sm={6} md={3} key={stat.label}>
                        <Card sx={{ height: '100%' }}>
                            <CardContent>
                                <Box display="flex" justifyContent="space-between" alignItems="flex-start">
                                    <Box>
                                        <Typography variant="h4" fontWeight={700}>
                                            {stat.value}
                                        </Typography>
                                        <Typography variant="body2" color="text.secondary" mt={0.5}>
                                            {stat.label}
                                        </Typography>
                                    </Box>
                                    <Box sx={{ color: stat.color, opacity: 0.9 }}>{stat.icon}</Box>
                                </Box>
                            </CardContent>
                        </Card>
                    </Grid>
                ))}
            </Grid>

            {/* Vulnerability Chart */}
            <Card>
                <CardContent>
                    <Typography variant="subtitle1" fontWeight={600} mb={2}>
                        District Vulnerability Index
                    </Typography>
                    {vulnData.length === 0 ? (
                        <Typography color="text.secondary" variant="body2">
                            No district data available.
                        </Typography>
                    ) : (
                        <ResponsiveContainer width="100%" height={220}>
                            <AreaChart data={vulnData} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
                                <defs>
                                    <linearGradient id="vIdx" x1="0" y1="0" x2="0" y2="1">
                                        <stop offset="5%" stopColor="#f87171" stopOpacity={0.4} />
                                        <stop offset="95%" stopColor="#f87171" stopOpacity={0} />
                                    </linearGradient>
                                </defs>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                <XAxis dataKey="name" tick={{ fontSize: 11, fill: '#94a3b8' }} />
                                <YAxis domain={[0, 1]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                                <Tooltip
                                    contentStyle={{ background: '#111e35', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}
                                    labelStyle={{ color: '#e2e8f0' }}
                                />
                                <Area
                                    type="monotone" dataKey="index"
                                    stroke="#f87171" strokeWidth={2}
                                    fill="url(#vIdx)"
                                />
                            </AreaChart>
                        </ResponsiveContainer>
                    )}
                </CardContent>
            </Card>
        </Box>
    );
};

export default DashboardPage;
