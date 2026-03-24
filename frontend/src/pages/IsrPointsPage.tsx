import { useState } from 'react';
import { Box, Typography, Button, Alert, Chip } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { AddOutlined, PlayArrowOutlined } from '@mui/icons-material';
import { useFetchIsrPoints, useCreateIsrPoint, useRunSimulation } from '@/hooks/useFetchIsrPoints';
import { IsrPointForm } from '@/components/forms/IsrPointForm';
import type { IsrPointCreate } from '@/types/simulation';
import { useNavigate } from 'react-router-dom';

const IsrPointsPage: React.FC = () => {
    const { data: isrPoints = [], isLoading } = useFetchIsrPoints();
    const createMutation = useCreateIsrPoint();
    const runSimulation = useRunSimulation();
    const navigate = useNavigate();

    const [formOpen, setFormOpen] = useState(false);
    const [runningId, setRunningId] = useState<string | null>(null);

    const handleRun = async (isrId: string) => {
        setRunningId(isrId);
        try {
            const result = await runSimulation.mutateAsync({ isrId });
            navigate(`/simulations/${result.simulation_id}`);
        } catch (_) {
            setRunningId(null);
        }
    };

    const columns: GridColDef[] = [
        { field: 'name', headerName: 'Name', flex: 1 },
        {
            field: 'injection_rate', headerName: 'Rate (m³/d)', width: 120,
            valueFormatter: ({ value }) => value != null ? `${value as number}` : '—',
        },
        {
            field: 'injection_start_date', headerName: 'Start', width: 120,
            valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : '—',
        },
        {
            field: 'injection_end_date', headerName: 'End', width: 120,
            valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : '—',
        },
        {
            field: 'actions', headerName: '', width: 160,
            renderCell: ({ row }: { row: { id: string } }) => (
                <Button
                    startIcon={<PlayArrowOutlined />}
                    size="small"
                    variant="outlined"
                    color="secondary"
                    disabled={runningId === row.id}
                    onClick={() => handleRun(row.id)}
                >
                    {runningId === row.id ? 'Running…' : 'Run Sim'}
                </Button>
            ),
        },
    ];

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h5" fontWeight={700}>ISR Points</Typography>
                <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setFormOpen(true)}>
                    New ISR Point
                </Button>
            </Box>

            {runSimulation.isError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                    Failed to run simulation. Check hydrogeological data availability.
                </Alert>
            )}

            <DataGrid
                rows={isrPoints} columns={columns} loading={isLoading}
                autoHeight disableRowSelectionOnClick
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}
            />

            <IsrPointForm
                open={formOpen}
                onClose={() => setFormOpen(false)}
                onSubmit={(vals: IsrPointCreate) => createMutation.mutateAsync(vals)}
                loading={createMutation.isPending}
            />
        </Box>
    );
};

export default IsrPointsPage;
