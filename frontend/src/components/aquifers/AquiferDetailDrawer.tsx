import React from 'react';
import { Drawer, Box, Typography, IconButton, List, ListItem, ListItemText, CircularProgress, Chip, Divider } from '@mui/material';
import { CloseOutlined, SensorsOutlined } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { aquifersApi } from '@/api/aquifersApi';
import { useMonitoringData } from '@/hooks/useMonitoringQueries';

interface Props {
    aquiferId: string | null;
    onClose: () => void;
}

export const AquiferDetailDrawer: React.FC<Props> = ({ aquiferId, onClose }) => {
    const { data: aquifer, isLoading: loadingAquifer } = useQuery({
        queryKey: ['aquifers', aquiferId, 'detail'],
        queryFn: () => aquifersApi.getById(aquiferId!),
        enabled: !!aquiferId,
    });

    const { data: monitoringData, isLoading: loadingMonitoring } = useMonitoringData(aquiferId ?? undefined);

    const isLoading = loadingAquifer || loadingMonitoring;

    return (
        <Drawer
            anchor="right"
            open={!!aquiferId}
            onClose={onClose}
            PaperProps={{ sx: { width: 380, bgcolor: 'background.paper', p: 0 } }}
            elevation={16}
        >
            <Box display="flex" flexDirection="column" height="100%">
                <Box p={2.5} display="flex" justifyContent="space-between" alignItems="center" borderBottom="1px solid" borderColor="divider">
                    <Typography variant="subtitle1" fontWeight={700}>
                        {aquifer?.name || 'Aquifer Details'}
                    </Typography>
                    <IconButton onClick={onClose} size="small">
                        <CloseOutlined />
                    </IconButton>
                </Box>

                {isLoading ? (
                    <Box p={4} display="flex" justifyContent="center"><CircularProgress size={30} /></Box>
                ) : aquifer ? (
                    <Box p={2.5} flex={1} overflow="auto">
                        <Typography variant="overline" color="text.secondary">Properties</Typography>
                        <List disablePadding sx={{ mb: 3 }}>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Type" secondary={aquifer.type || '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Hydraulic Conductivity" secondary={aquifer.hydraulic_conductivity ? `${aquifer.hydraulic_conductivity.toFixed(4)} m/d` : '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Transmissivity" secondary={aquifer.transmissivity ? `${aquifer.transmissivity.toFixed(2)} m²/d` : '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Porosity" secondary={aquifer.porosity ? `${aquifer.porosity.toFixed(3)}` : '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Depth to Water (DTW)" secondary={aquifer.dtw_decadal_avg ? `${aquifer.dtw_decadal_avg.toFixed(1)} m` : '—'} />
                            </ListItem>
                        </List>

                        <Divider sx={{ mb: 2 }} />
                        <Typography variant="overline" color="text.secondary">Recent Monitoring Activity</Typography>
                        
                        {!monitoringData || monitoringData.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" py={1}>No active monitoring stations for this aquifer.</Typography>
                        ) : (
                            <List disablePadding>
                                {/* Assuming monitoringData is an array of stations/readings */}
                                {(monitoringData as any[]).map((station, idx) => (
                                    <ListItem key={idx} disableGutters divider>
                                        <ListItemText 
                                            primary={
                                                <Box display="flex" alignItems="center" gap={1}>
                                                    <SensorsOutlined fontSize="small" color="primary" />
                                                    {station.name || 'Station'}
                                                </Box>
                                            } 
                                            secondary={`Uranium: ${station.lastReading?.uranium_concentration || 'N/A'} μg/L`} 
                                        />
                                        <Chip 
                                            label={station.status || 'Active'} 
                                            size="small" 
                                            color={station.status === 'alert' ? 'error' : 'success'} 
                                            sx={{ height: 20, fontSize: 10 }}
                                        />
                                    </ListItem>
                                ))}
                            </List>
                        )}
                    </Box>
                ) : null}
            </Box>
        </Drawer>
    );
};
