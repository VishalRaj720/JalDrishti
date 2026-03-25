import { useState } from 'react';
import { Box, Typography, Button, Chip } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { AddOutlined } from '@mui/icons-material';
import { useFetchDistricts, useDeleteDistrict } from '@/hooks/useFetchDistricts';
import { useRBAC } from '@/hooks/useRBAC';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { vulnerabilityColor } from '@/utils/geoUtils';
import { DistrictDetailDrawer } from '@/components/districts/DistrictDetailDrawer';

const columns = (onDelete: (id: string) => void, canDelete: boolean, onView: (id: string) => void): GridColDef[] => [
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
    {
        field: 'view', headerName: '', width: 80,
        renderCell: ({ row }) => (
            <Button size="small" onClick={() => onView(row.id)}>View</Button>
        ),
    },
    ...(canDelete ? [{
        field: 'actions', headerName: '', width: 80,
        renderCell: ({ row }: { row: { id: string } }) => (
            <Button size="small" color="error" onClick={() => onDelete(row.id)}>Delete</Button>
        ),
    } as GridColDef] : []),
];

const DistrictsPage: React.FC = () => {
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
    const { data: districts = [], isLoading } = useFetchDistricts(
        paginationModel.page * paginationModel.pageSize,
        paginationModel.pageSize
    );
    const deleteMutation = useDeleteDistrict();
    const { canDelete } = useRBAC();
    const [deleteId, setDeleteId] = useState<string | null>(null);
    const [viewId, setViewId] = useState<string | null>(null);

    // Approximate rowCount based on length
    const rowCount = districts.length === paginationModel.pageSize ? -1 : paginationModel.page * paginationModel.pageSize + districts.length;

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h5" fontWeight={700}>Districts</Typography>
            </Box>

            <DataGrid
                rows={districts}
                columns={columns((id) => setDeleteId(id), canDelete, (id) => setViewId(id))}
                loading={isLoading}
                autoHeight
                disableRowSelectionOnClick
                paginationMode="server"
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                rowCount={rowCount}
                pageSizeOptions={[25, 50, 100]}
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
            <DistrictDetailDrawer districtId={viewId} onClose={() => setViewId(null)} />
        </Box>
    );
};

export default DistrictsPage;
