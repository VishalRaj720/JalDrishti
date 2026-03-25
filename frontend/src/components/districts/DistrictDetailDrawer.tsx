import React from 'react';
import { Drawer, Box, Typography, IconButton, List, ListItem, ListItemText, Chip } from '@mui/material';
import { CloseOutlined, ContentCut } from '@mui/icons-material';
import { useFetchDistrictDetail } from '@/hooks/useFetchDistricts';
import { vulnerabilityColor } from '@/utils/geoUtils';

interface Props {
    districtId: string | null;
    onClose: () => void;
}

export const DistrictDetailDrawer: React.FC<Props> = ({ districtId, onClose }) => {
    const { data: detail, isLoading } = useFetchDistrictDetail(districtId);

    return (
        <Drawer
            anchor="right"
            open={!!districtId}
            onClose={onClose}
            PaperProps={{ sx: { width: 350, bgcolor: 'background.paper', p: 0 } }}
            elevation={16}
        >
            <Box display="flex" flexDirection="column" height="100%">
                <Box p={2.5} display="flex" justifyContent="space-between" alignItems="center" borderBottom="1px solid" borderColor="divider">
                    <Typography variant="subtitle1" fontWeight={700}>
                        {isLoading ? 'Loading...' : detail?.name || 'District Details'}
                    </Typography>
                    <IconButton onClick={onClose} size="small">
                        <CloseOutlined />
                    </IconButton>
                </Box>

                {detail && (
                    <Box p={2.5} flex={1} overflow="auto">
                        <Typography variant="overline" color="text.secondary">Vulnerability Specs</Typography>
                        <List disablePadding sx={{ mb: 3 }}>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Risk Index" />
                                {detail.vulnerability_index != null ? (
                                    <Chip label={detail.vulnerability_index.toFixed(2)} size="small" color={vulnerabilityColor(detail.vulnerability_index)} />
                                ) : '—'}
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Avg Porosity" secondary={detail.avg_porosity?.toFixed(3) ?? '—'} />
                            </ListItem>
                            <ListItem disableGutters sx={{ py: 0.5 }}>
                                <ListItemText primary="Avg Hydraulic Cond." secondary={detail.avg_hydraulic_conductivity?.toFixed(4) ?? '—'} />
                            </ListItem>
                        </List>

                        <Typography variant="overline" color="text.secondary">Associated Blocks ({detail.blocks.length})</Typography>
                        {detail.blocks.length === 0 ? (
                            <Typography variant="body2" color="text.secondary" py={2}>No blocks recorded.</Typography>
                        ) : (
                            <List disablePadding>
                                {detail.blocks.map(b => (
                                    <ListItem key={b.id} disableGutters divider>
                                        <ListItemText primary={b.name} secondary={b.avg_porosity ? `Porosity: ${b.avg_porosity.toFixed(3)}` : ''} />
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
