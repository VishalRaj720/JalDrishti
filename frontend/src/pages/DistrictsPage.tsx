import { useState } from 'react';
import { Box, Typography, Button, Chip } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { AddOutlined } from '@mui/icons-material';
import { useFetchDistricts, useDeleteDistrict } from '@/hooks/useFetchDistricts';
import { useRBAC } from '@/hooks/useRBAC';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { vulnerabilityColor } from '@/utils/geoUtils';

const columns = (onDelete: (id: string) => void, canDelete: boolean): GridColDef[] => [
    { field: 'name', headerName: 'District', flex: 1 },
    {
        field: 'vulnerability_index',
        headerName: 'Vulnerability',
        width: 150,
        renderCell: ({ value }) => {
            const v = value as number | null;
            return v != null ? (
                <Chip label={v.toFixed(2)} color={vulnerabilityColor(v)} size="small" />
            ) : '—';
        },
    },
    {
        field: 'avg_porosity',
        headerName: 'Avg Porosity',
        width: 130,
        valueFormatter: ({ value }) => value != null ? (value as number).toFixed(3) : '—',
    },
    {
        field: 'avg_hydraulic_conductivity',
        headerName: 'Hyd. Cond. (m/d)',
        width: 160,
        valueFormatter: ({ value }) => value != null ? (value as number).toFixed(4) : '—',
    },
    {
        field: 'created_at',
        headerName: 'Created',
        width: 150,
        valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : '—',
    },
    ...(canDelete ? [{
        field: 'actions', headerName: '', width: 100,
        renderCell: ({ row }: { row: { id: string } }) => (
            <Button size="small" color="error" onClick={() => onDelete(row.id)}>Delete</Button>
        ),
    } as GridColDef] : []),
];

const DistrictsPage: React.FC = () => {
    const { data: districts = [], isLoading } = useFetchDistricts();
    const deleteMutation = useDeleteDistrict();
    const { canDelete } = useRBAC();
    const [deleteId, setDeleteId] = useState<string | null>(null);

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h5" fontWeight={700}>Districts</Typography>
            </Box>

            <DataGrid
                rows={districts}
                columns={columns((id) => setDeleteId(id), canDelete)}
                loading={isLoading}
                autoHeight
                disableRowSelectionOnClick
                sx={{
                    border: '1px solid',
                    borderColor: 'divider',
                    borderRadius: 2,
                    '& .MuiDataGrid-row:hover': { bgcolor: 'rgba(56,189,248,0.04)' },
                }}
            />

            <ConfirmDialog
                open={!!deleteId}
                message="Delete this district? This action cannot be undone."
                onConfirm={async () => {
                    if (deleteId) await deleteMutation.mutateAsync(deleteId);
                    setDeleteId(null);
                }}
                onCancel={() => setDeleteId(null)}
                loading={deleteMutation.isPending}
            />
        </Box>
    );
};

export default DistrictsPage;
