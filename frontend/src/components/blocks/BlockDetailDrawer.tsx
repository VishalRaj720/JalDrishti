import React from 'react';
import { Drawer, Box, Typography, IconButton, List, ListItem, ListItemText, Chip, Divider } from '@mui/material';
import { CloseOutlined, WaterDropOutlined, SensorsOutlined } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import axiosInstance from '@/api/axiosInstance';
import { useFetchBlockDetail } from '@/hooks/useFetchGlobalBlocks';

interface Props {
    districtId: string | null;
    blockId: string | null;
    onClose: () => void;
}

export const BlockDetailDrawer: React.FC<Props> = ({ districtId, blockId, onClose }) => {
    const { data: detail, isLoading } = useFetchBlockDetail(districtId, blockId);

    const { data: stations = [] } = useQuery({
        queryKey: ['monitoring-stations', 'block', blockId],
        queryFn: () => axiosInstance.get(`/blocks/${blockId}/monitoring-stations`).then(r => r.data),
        enabled: !!blockId,
    });

    return (
        <Drawer
            anchor="right"
            open={!!blockId}
            onClose={onClose}
            PaperProps={{ sx: { width: 350, bgcolor: 'background.paper', p: 0 } }}
            elevation={16}
        >
            <Box display="flex" flexDirection="column" height="100%">
                <Box p={2.5} display="flex" justifyContent="space-between" alignItems="center" borderBottom="1px solid" borderColor="divider">
                    <Typography variant="subtitle1" fontWeight={700}>
                        {isLoading ? 'Loading...' : detail?.name || 'Block Details'}
                    </Typography>
                    <IconButton onClick={onClose} size="small">
                        <CloseOutlined />
                    </IconButton>
                </Box>

                {detail && (
                    <Box p={2.5} flex={1} overflow="auto">
                        <Typography variant="overline" color="text.secondary">Properties</Typography>
                        <List disablePadding sx={{ mb: 3 }}>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Avg Porosity" secondary={detail.avg_porosity?.toFixed(3) ?? '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Avg Permeability" secondary={detail.avg_permeability?.toFixed(3) ?? '—'} />
                            </ListItem>
                        </List>

                        <Typography variant="overline" color="text.secondary">Aquifers ({detail.aquifers.length})</Typography>
                        {detail.aquifers.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" py={2}>No aquifers located.</Typography>
                        ) : (
                            <List disablePadding>
                                {detail.aquifers.map(a => (
                                    <ListItem key={a.id} disableGutters divider>
                                        <ListItemText 
                                            primary={<Box display="flex" alignItems="center" gap={1}><WaterDropOutlined fontSize="small" color="primary" /> {a.name}</Box>} 
                                            secondary={a.type ? `Type: ${a.type}` : ''} 
                                        />
                                    </ListItem>
                                ))}
                            </List>
                        )}

                        <Divider sx={{ my: 2 }} />
                        <Typography variant="overline" color="text.secondary">Monitoring Stations ({stations.length})</Typography>
                        {stations.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" py={2}>No active stations in this block.</Typography>
                        ) : (
                            <List disablePadding>
                                {stations.map((s: any) => (
                                    <ListItem key={s.id} disableGutters divider>
                                        <ListItemText 
                                            primary={<Box display="flex" alignItems="center" gap={1}><SensorsOutlined fontSize="small" color="info" /> {s.name}</Box>} 
                                            secondary={`Depth: ${s.well_depth ? s.well_depth + ' m' : 'N/A'}`} 
                                        />
                                    </ListItem>
                                ))}
                            </List>
                        )}
                    </Box>
                )}
            </Box>
        </Drawer>
    );
};
