import { Dialog, DialogTitle, DialogContent, DialogActions, Button, TextField, Grid, Slider, Typography } from '@mui/material';
import { useFormik } from 'formik';
import * as Yup from 'yup';
import type { IsrPointCreate } from '@/types/simulation';

interface Props {
    open: boolean;
    onClose: () => void;
    onSubmit: (values: IsrPointCreate) => Promise<unknown>;
    loading?: boolean;
}

const schema = Yup.object({
    name: Yup.string().required('Name is required'),
    injection_rate: Yup.number().min(0).nullable(),
});

export const IsrPointForm: React.FC<Props> = ({ open, onClose, onSubmit, loading }) => {
    const formik = useFormik<IsrPointCreate>({
        initialValues: { name: '', injection_rate: 10 },
        validationSchema: schema,
        onSubmit: async (values) => {
            await onSubmit(values);
            onClose();
        },
    });

    return (
        <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
            <form onSubmit={formik.handleSubmit}>
                <DialogTitle>Create ISR Point</DialogTitle>
                <DialogContent>
                    <Grid container spacing={2} sx={{ mt: 0.5 }}>
                        <Grid item xs={12}>
                            <TextField
                                fullWidth label="Name" id="name" name="name"
                                value={formik.values.name} onChange={formik.handleChange}
                                error={!!formik.errors.name} helperText={formik.errors.name}
                            />
                        </Grid>
                        <Grid item xs={12}>
                            <Typography gutterBottom variant="body2" color="text.secondary">
                                Injection Rate (m³/day): <strong>{formik.values.injection_rate}</strong>
                            </Typography>
                            <Slider
                                id="injection_rate" name="injection_rate"
                                min={0} max={500} step={1}
                                value={formik.values.injection_rate ?? 0}
                                onChange={(_, val) => formik.setFieldValue('injection_rate', val)}
                                color="primary"
                                marks={[{ value: 0, label: '0' }, { value: 500, label: '500' }]}
                            />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                            <TextField
                                fullWidth label="Injection Start Date" id="injection_start_date"
                                name="injection_start_date" type="date"
                                InputLabelProps={{ shrink: true }}
                                value={formik.values.injection_start_date ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                        <Grid item xs={12} sm={6}>
                            <TextField
                                fullWidth label="Injection End Date" id="injection_end_date"
                                name="injection_end_date" type="date"
                                InputLabelProps={{ shrink: true }}
                                value={formik.values.injection_end_date ?? ''}
                                onChange={formik.handleChange}
                            />
                        </Grid>
                    </Grid>
                </DialogContent>
                <DialogActions>
                    <Button onClick={onClose} color="inherit" disabled={loading}>Cancel</Button>
                    <Button type="submit" variant="contained" disabled={loading}>Save</Button>
                </DialogActions>
            </form>
        </Dialog>
    );
};
