import React from 'react';
import {
    Drawer, Box, Typography, IconButton,
    Button, CircularProgress, List, ListItem, ListItemText, Chip
} from '@mui/material';
import { CloseOutlined, PlayArrowOutlined, ScienceOutlined } from '@mui/icons-material';
import { useMapContext } from '@/contexts/MapContext';
import { useFetchIsrPoints } from '@/hooks/useFetchIsrPoints';
import { useSimulationsByIsr } from '@/hooks/useMonitoringQueries';
import { simulationsApi } from '@/api/simulationsApi';
import { useNavigate } from 'react-router-dom';
import type { Simulation } from '@/types/simulation';
import { useMutation, useQueryClient } from '@tanstack/react-query';

export const IsrPointDetailDrawer: React.FC = () => {
    const { selectedIsrId, setSelectedIsrId } = useMapContext();
    const { data: isrPoints = [] } = useFetchIsrPoints();
    const { data: simulations = [], isLoading: loadingSims } = useSimulationsByIsr(selectedIsrId ?? undefined);
    
    const navigate = useNavigate();
    const queryClient = useQueryClient();

    const isr = isrPoints.find(p => p.id === selectedIsrId);
    
    const runMutation = useMutation({
        mutationFn: () => simulationsApi.run(selectedIsrId!),
        onSuccess: (sim: Simulation) => {
            queryClient.invalidateQueries({ queryKey: ['simulations'] });
            navigate(`/simulations/${sim.id}`);
            setSelectedIsrId(null);
        }
    });

    const isActive = isr?.injection_start_date && 
        (!isr.injection_end_date || new Date(isr.injection_end_date) > new Date());

    return (
        <Drawer
            anchor="right"
            open={!!selectedIsrId}
            onClose={() => setSelectedIsrId(null)}
            PaperProps={{ sx: { width: 350, bgcolor: 'background.paper', backgroundImage: 'none', p: 0 } }}
            variant="temporary"
            elevation={16}
            hideBackdrop={false} // Allow clicking Map outside to close if true, or keep backdrop, wait MapView is not full screen!
            ModalProps={{ container: document.getElementById('root') }} // Attach to root so it floats above everything safely
        >
            {isr && (
                <Box display="flex" flexDirection="column" height="100%">
                    <Box p={2.5} display="flex" justifyContent="space-between" alignItems="center" borderBottom="1px solid" borderColor="divider">
                        <Box display="flex" alignItems="center" gap={1.5}>
                            <Box sx={{ color: isActive ? 'error.main' : 'warning.main', display: 'flex' }}>
                                <ScienceOutlined />
                            </Box>
                            <Box>
                                <Typography variant="subtitle1" fontWeight={700} lineHeight={1.2}>
                                    {isr.name}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                    {isActive ? '🔴 Active Injection' : '⚪ Inactive'}
                                </Typography>
                            </Box>
                        </Box>
                        <IconButton onClick={() => setSelectedIsrId(null)} size="small">
                            <CloseOutlined />
                        </IconButton>
                    </Box>

                    <Box p={2.5} flex={1} overflow="auto">
                        <Typography variant="overline" color="text.secondary">Details</Typography>
                        <List disablePadding sx={{ mb: 3 }}>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Injection Rate" secondary={`${isr.injection_rate ?? '—'} m³/day`} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText 
                                    primary="Operation Period" 
                                    secondary={isr.injection_start_date ? `${new Date(isr.injection_start_date).toLocaleDateString()} to ${isr.injection_end_date ? new Date(isr.injection_end_date).toLocaleDateString() : 'Present'}` : '—'} 
                                />
                            </ListItem>
                        </List>

                        <Typography variant="overline" color="text.secondary">Simulation History</Typography>
                        {loadingSims ? (
                            <Box display="flex" justifyContent="center" py={4}><CircularProgress size={24} /></Box>
                        ) : simulations.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" py={2}>
                                No simulations run for this point yet.
                            </Typography>
                        ) : (
                            <List disablePadding>
                                {[...simulations].sort((a,b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()).slice(0, 5).map(sim => (
                                    <ListItem 
                                        key={sim.id} 
                                        disableGutters 
                                        divider
                                        sx={{ cursor: 'pointer', '&:hover': { bgcolor: 'action.hover' }, px: 1, borderRadius: 1 }}
                                        onClick={() => navigate(`/simulations/${sim.id}`)}
                                    >
                                        <ListItemText
                                            primary={
                                                <Box display="flex" justifyContent="space-between" mb={0.5}>
                                                    <Typography variant="body2" fontWeight={600}>{sim.id.substring(0,8)}</Typography>
                                                    <Chip 
                                                        label={sim.status} 
                                                        size="small" 
                                                        color={sim.status === 'completed' ? 'success' : sim.status === 'failed' ? 'error' : 'warning'} 
                                                        sx={{ height: 18, fontSize: '0.65rem' }}
                                                    />
                                                </Box>
                                            }
                                            secondary={new Date(sim.created_at).toLocaleDateString()}
                                        />
                                    </ListItem>
                                ))}
                            </List>
                        )}
                    </Box>

                    <Box p={2} borderTop="1px solid" borderColor="divider" bgcolor="background.default">
                        <Button
                            variant="contained"
                            color="primary"
                            fullWidth
                            startIcon={runMutation.isPending ? <CircularProgress size={16} /> : <PlayArrowOutlined />}
                            onClick={() => runMutation.mutate()}
                            disabled={runMutation.isPending}
                        >
                            {runMutation.isPending ? 'Starting...' : 'Run New Simulation'}
                        </Button>
                    </Box>
                </Box>
            )}
        </Drawer>
    );
};
