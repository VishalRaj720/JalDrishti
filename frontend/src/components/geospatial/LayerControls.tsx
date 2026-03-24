import {
    Box, Paper, Typography, FormGroup, FormControlLabel, Switch, Divider,
} from '@mui/material';
import { useMapContext, type LayerKey } from '@/contexts/MapContext';

const LAYER_LABELS: Record<LayerKey, string> = {
    districts: 'Districts',
    blocks: 'Blocks',
    aquifers: 'Aquifers',
    isr_points: 'ISR Points',
    plumes: 'Plumes',
};

export const LayerControls: React.FC = () => {
    const { layers, setLayerVisible } = useMapContext();

    return (
        <Paper sx={{ p: 2, minWidth: 180 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600} letterSpacing="0.08em">
                MAP LAYERS
            </Typography>
            <Divider sx={{ my: 1 }} />
            <FormGroup>
                {(Object.keys(layers) as LayerKey[]).map((key) => (
                    <FormControlLabel
                        key={key}
                        control={
                            <Switch
                                size="small"
                                checked={layers[key].visible}
                                onChange={(_, checked) => setLayerVisible(key, checked)}
                                color="primary"
                            />
                        }
                        label={<Typography variant="body2">{LAYER_LABELS[key]}</Typography>}
                    />
                ))}
            </FormGroup>
        </Paper>
    );
};
