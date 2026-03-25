import React, { Suspense, lazy } from 'react';
import {
    Box, Grid, Typography, Card, CardContent,
    List, ListItem, ListItemText, Chip, Divider
} from '@mui/material';
import {
    ScienceOutlined, WarningOutlined, MapOutlined, SensorsOutlined, DoneAllOutlined,
} from '@mui/icons-material';
import {
    ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell,
} from 'recharts';
import { useQuery } from '@tanstack/react-query';
import axiosInstance from '@/api/axiosInstance';
import { useFetchDistricts } from '@/hooks/useFetchDistricts';
import { useFetchAquifers } from '@/hooks/useFetchAquifers';
import { useFetchIsrPoints } from '@/hooks/useFetchIsrPoints';
import { useAuth } from '@/hooks/useAuth';
import { useAlerts } from '@/hooks/useAlerts';
import { simulationsApi } from '@/api/simulationsApi';
import { AlertsBanner } from '@/components/common/AlertsBanner';
import { AquiferDataCompletenessPanel } from '@/components/dashboard/AquiferDataCompletenessPanel';
import LoadingSpinner from '@/components/common/LoadingSpinner';

const MapView = lazy(() => import('@/components/geospatial/MapView'));

const DashboardPage: React.FC = () => {
    const { user } = useAuth();
    const { data: districts = [] } = useFetchDistricts();
    const { data: aquifers = [] } = useFetchAquifers();
    const { data: isrPoints = [] } = useFetchIsrPoints();
    const { data: simsTodayCount = 0 } = useQuery({
        queryKey: ['simulations', 'count', 'today'],
        queryFn: () => simulationsApi.getAll().then(res => res.filter(s => s.created_at.startsWith(new Date().toISOString().split('T')[0])).length),
        staleTime: 60 * 1000,
    });
    
    // Efficiently count stations via database
    const { data: allStationsCount = 0 } = useQuery({
        queryKey: ['monitoring-stations', 'count'],
        queryFn: () => axiosInstance.get('/monitoring-stations/count').then(r => r.data),
        staleTime: 5 * 60 * 1000,
    });
    
    const alerts = useAlerts();

    // ── Data Processing ───────────────────────────────────────────
    const activeInjections = isrPoints.filter(isr => 
        isr.injection_start_date && 
        (!isr.injection_end_date || new Date(isr.injection_end_date) > new Date())
    ).length;

    const highRiskDistricts = districts.filter(d => (d.vulnerability_index ?? 0) > 0.66).length;
    
    const aquifersWithPorosity = aquifers.filter(a => a.porosity != null).length;
    const completenessPct = Math.round((aquifersWithPorosity / Math.max(aquifers.length, 1)) * 100);

    // ── Chart Data ────────────────────────────────────────────────
    const vulnData = districts
        .map(d => ({
            name: d.name.substring(0, 10),
            index: Number(d.vulnerability_index?.toFixed(2) ?? 0),
        }))
        .sort((a, b) => b.index - a.index)
        .slice(0, 10); // Show top 10 most vulnerable

    // ── Recent Simulations ────────────────────────────────────────
    // Since we removed full sims fetch for count, fetch just latest 5
    const { data: recentSims = [] } = useQuery({
        queryKey: ['simulations', 'recent'],
        queryFn: () => simulationsApi.getAll().then(res => res.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5)),
        staleTime: 30 * 1000,
    });

    // ── Stats Config ──────────────────────────────────────────────
    const stats = [
        { label: 'Active Injections', value: activeInjections, icon: <ScienceOutlined />, color: 'primary.main' },
        { label: 'High-Risk Districts', value: highRiskDistricts, icon: <WarningOutlined />, color: 'error.main' },
        { label: 'Total Monitoring Sites', value: allStationsCount, icon: <SensorsOutlined />, color: 'info.main' },
        { label: 'Simulations Today', value: simsTodayCount, icon: <MapOutlined />, color: 'secondary.main' },
        { label: 'Data Completeness %', value: `${completenessPct}%`, icon: <DoneAllOutlined />, color: 'success.main' },
    ];

    return (
        <Box>
            <AlertsBanner alerts={alerts} />
            
            <Typography variant="h5" fontWeight={700} mb={0.5}>
                Dashboard
            </Typography>
            <Typography variant="body2" color="text.secondary" mb={3}>
                Welcome back, <strong>{user?.username}</strong>
            </Typography>

            {/* KPI Cards */}
            <Grid container spacing={2} mb={3}>
                {stats.map((stat) => (
                    <Grid item xs={12} sm={6} md={2.4} key={stat.label}>
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

            {/* Split Layout: Mini-map & Recent Sims */}
            <Grid container spacing={2} mb={3}>
                <Grid item xs={12} md={8}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                            <Typography variant="subtitle1" fontWeight={600} mb={2}>
                                System Overview Map
                            </Typography>
                            <Box flexGrow={1} minHeight={300} position="relative">
                                <Suspense fallback={<LoadingSpinner />}>
                                    <MapView height="100%" />
                                </Suspense>
                            </Box>
                        </CardContent>
                    </Card>
                </Grid>
                <Grid item xs={12} md={4}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" fontWeight={600} mb={2}>
                                Recent Simulations
                            </Typography>
                            {recentSims.length === 0 ? (
                                <Typography variant="body2" color="text.secondary">No simulations found.</Typography>
                            ) : (
                                <List disablePadding>
                                    {recentSims.map((sim, i) => (
                                        <React.Fragment key={sim.id}>
                                            <ListItem alignItems="flex-start" disableGutters>
                                                <ListItemText
                                                    primary={
                                                        <Box display="flex" justifyContent="space-between">
                                                            <Typography variant="body2" fontWeight={600}>
                                                                {sim.id.substring(0, 8)}
                                                            </Typography>
                                                            <Chip 
                                                                label={sim.status} 
                                                                size="small" 
                                                                color={sim.status === 'completed' ? 'success' : sim.status === 'failed' ? 'error' : 'warning'} 
                                                                sx={{ height: 20, fontSize: '0.65rem' }}
                                                            />
                                                        </Box>
                                                    }
                                                    secondary={
                                                        <Typography variant="caption" color="text.secondary" display="block">
                                                            Area: {sim.affected_area ? `${(sim.affected_area / 1e6).toFixed(2)} km²` : '—'} <br/>
                                                            {new Date(sim.created_at).toLocaleString()}
                                                        </Typography>
                                                    }
                                                />
                                            </ListItem>
                                            {i < recentSims.length - 1 && <Divider component="li" />}
                                        </React.Fragment>
                                    ))}
                                </List>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>

            {/* Charts Row */}
            <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                    <Card sx={{ height: '100%' }}>
                        <CardContent>
                            <Typography variant="subtitle1" fontWeight={600} mb={2}>
                                Most Vulnerable Districts
                            </Typography>
                            {vulnData.length === 0 ? (
                                <Typography color="text.secondary" variant="body2">No data available.</Typography>
                            ) : (
                                <ResponsiveContainer width="100%" height={250}>
                                    <BarChart data={vulnData} layout="vertical" margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="rgba(255,255,255,0.06)" />
                                        <XAxis type="number" domain={[0, 1]} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                                        <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 11, fill: '#94a3b8' }} />
                                        <Tooltip
                                            contentStyle={{ background: '#111e35', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8 }}
                                        />
                                        <Bar dataKey="index" radius={[0, 4, 4, 0]}>
                                            {vulnData.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.index > 0.66 ? '#f87171' : entry.index > 0.33 ? '#fbbf24' : '#34d399'} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            )}
                        </CardContent>
                    </Card>
                </Grid>
                <Grid item xs={12} md={6}>
                    <AquiferDataCompletenessPanel />
                </Grid>
            </Grid>
        </Box>
    );
};

export default DashboardPage;
