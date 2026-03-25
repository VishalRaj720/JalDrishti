import { useState } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { AddOutlined } from '@mui/icons-material';
import { useFetchAquifers, useCreateAquifer, useDeleteAquifer } from '@/hooks/useFetchAquifers';
import { useRBAC } from '@/hooks/useRBAC';
import { AquiferForm } from '@/components/forms/AquiferForm';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import type { AquiferCreate } from '@/types/aquifer';
import { AquiferDetailDrawer } from '@/components/aquifers/AquiferDetailDrawer';

const AquifersPage: React.FC = () => {
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
    const { data: aquifers = [], isLoading } = useFetchAquifers(
        undefined,
        paginationModel.page * paginationModel.pageSize,
        paginationModel.pageSize
    );
    const createMutation = useCreateAquifer();
    const deleteMutation = useDeleteAquifer();
    const { canCreateEdit, canDelete } = useRBAC();

    const [formOpen, setFormOpen] = useState(false);
    const [deleteId, setDeleteId] = useState<string | null>(null);
    const [viewId, setViewId] = useState<string | null>(null);

    const rowCount = aquifers.length === paginationModel.pageSize ? -1 : paginationModel.page * paginationModel.pageSize + aquifers.length;

    const columns: GridColDef[] = [
        { field: 'name', headerName: 'Name', flex: 1 },
        { field: 'type', headerName: 'Type', width: 140 },
        {
            field: 'porosity', headerName: 'Porosity', width: 110,
            valueFormatter: ({ value }) => value != null ? (value as number).toFixed(3) : '—',
        },
        {
            field: 'hydraulic_conductivity', headerName: 'Hyd. Cond.', width: 130,
            valueFormatter: ({ value }) => value != null ? (value as number).toFixed(4) : '—',
        },
        {
            field: 'transmissivity', headerName: 'Transmissivity', width: 140,
            valueFormatter: ({ value }) => value != null ? (value as number).toFixed(2) : '—',
        },
        {
            field: 'dtw_decadal_avg', headerName: 'DTW Avg (m)', width: 130,
            valueFormatter: ({ value }) => value != null ? (value as number).toFixed(1) : '—',
        },
        {
            field: 'updated_at', headerName: 'Last Updated', width: 140,
            valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : '—',
        },
        {
            field: 'view', headerName: '', width: 80,
            renderCell: ({ row }) => (
                <Button size="small" onClick={() => setViewId(row.id)}>View</Button>
            ),
        },
        ...(canDelete ? [{
            field: 'actions', headerName: '', width: 90,
            renderCell: ({ row }: { row: { id: string } }) => (
                <Button size="small" color="error" onClick={() => setDeleteId(row.id)}>Delete</Button>
            ),
        } as GridColDef] : []),
    ];

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h5" fontWeight={700}>Aquifers</Typography>
                {canCreateEdit && (
                    <Button variant="contained" startIcon={<AddOutlined />} onClick={() => setFormOpen(true)}>
                        New Aquifer
                    </Button>
                )}
            </Box>

            <DataGrid
                rows={aquifers} columns={columns} loading={isLoading}
                autoHeight disableRowSelectionOnClick
                paginationMode="server"
                paginationModel={paginationModel}
                onPaginationModelChange={setPaginationModel}
                rowCount={rowCount}
                pageSizeOptions={[25, 50, 100]}
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2 }}
            />

            <AquiferForm
                open={formOpen}
                onClose={() => setFormOpen(false)}
                onSubmit={(vals: AquiferCreate) => createMutation.mutateAsync(vals)}
                loading={createMutation.isPending}
            />

            <ConfirmDialog
                open={!!deleteId}
                message="Delete this aquifer? This cannot be undone."
                onConfirm={async () => {
                    if (deleteId) await deleteMutation.mutateAsync(deleteId);
                    setDeleteId(null);
                }}
                onCancel={() => setDeleteId(null)}
                loading={deleteMutation.isPending}
            />
            
            <AquiferDetailDrawer aquiferId={viewId} onClose={() => setViewId(null)} />
        </Box>
    );
};

export default AquifersPage;
