import {
    Dialog, DialogTitle, DialogContent, DialogActions,
    Button, TextField, MenuItem, Grid,
} from '@mui/material';
import { useFormik } from 'formik';
import * as Yup from 'yup';
import type { AquiferCreate } from '@/types/aquifer';
import { AQUIFER_TYPES } from '@/utils/constants';

interface Props {
    open: boolean;
    onClose: () => void;
    onSubmit: (values: AquiferCreate) => Promise<unknown>;
    loading?: boolean;
    initialValues?: Partial<AquiferCreate>;
}

const validationSchema = Yup.object({
    name: Yup.string().required('Name is required'),
    type: Yup.string().required('Type is required'),
    porosity: Yup.number().min(0).max(1).nullable(),
    hydraulic_conductivity: Yup.number().min(0).nullable(),
    transmissivity: Yup.number().min(0).nullable(),
});

export const AquiferForm: React.FC<Props> = ({ open, onClose, onSubmit, loading, initialValues }) => {
    const formik = useFormik<AquiferCreate>({
        initialValues: {
            name: initialValues?.name ?? '',
            type: initialValues?.type ?? 'unconfined',
            block_id: initialValues?.block_id,
            porosity: initialValues?.porosity,
            hydraulic_conductivity: initialValues?.hydraulic_conductivity,
            transmissivity: initialValues?.transmissivity,
            storage_coefficient: initialValues?.storage_coefficient,
            dtw_decadal_avg: initialValues?.dtw_decadal_avg,
        },
        validationSchema,
        enableReinitialize: true,
        onSubmit: async (values) => {
            await onSubmit(values);
            onClose();
        },
    });

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <form onSubmit={formik.handleSubmit}>
                <DialogTitle>Aquifer Details</DialogTitle>
                <DialogContent>
                    <Grid container spacing={2} sx={{ mt: 0.5 }}>
                        <Grid item xs={12} sm={8}>
                            <TextField
                                fullWidth label="Name" id="name" name="name"
                                value={formik.values.name}
                                onChange={formik.handleChange}
                                error={!!formik.errors.name}
                                helperText={formik.errors.name}
                            />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                            <TextField
                                fullWidth select label="Type" id="type" name="type"
                                value={formik.values.type}
                                onChange={formik.handleChange}
                            >
                                {AQUIFER_TYPES.map((t) => (
                                    <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                                ))}
                            </TextField>
                        </Grid>
                        <Grid item xs={12} sm={4}>
                            <TextField fullWidth label="Porosity (0–1)" id="porosity" name="porosity"
                                type="number" inputProps={{ step: 0.01, min: 0, max: 1 }}
                                value={formik.values.porosity ?? ''}
                                onChange={formik.handleChange}
                                error={!!formik.errors.porosity}
                                helperText={formik.errors.porosity as string}
                            />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                            <TextField fullWidth label="Hydraulic Conductivity (m/d)" id="hydraulic_conductivity" name="hydraulic_conductivity"
                                type="number" inputProps={{ step: 0.001 }}
                                value={formik.values.hydraulic_conductivity ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                        <Grid item xs={12} sm={4}>
                            <TextField fullWidth label="Transmissivity (m²/d)" id="transmissivity" name="transmissivity"
                                type="number" inputProps={{ step: 0.1 }}
                                value={formik.values.transmissivity ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                            <TextField fullWidth label="Storage Coefficient" id="storage_coefficient" name="storage_coefficient"
                                type="number" inputProps={{ step: 0.0001 }}
                                value={formik.values.storage_coefficient ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                            <TextField fullWidth label="DTW Decadal Avg (m)" id="dtw_decadal_avg" name="dtw_decadal_avg"
                                type="number" inputProps={{ step: 0.1 }}
                                value={formik.values.dtw_decadal_avg ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                    </Grid>
                </DialogContent>
                <DialogActions>
                    <Button onClick={onClose} color="inherit" disabled={loading}>Cancel</Button>
                    <Button type="submit" variant="contained" disabled={loading || formik.isSubmitting}>
                        Save
                    </Button>
                </DialogActions>
            </form>
        </Dialog>
    );
};
