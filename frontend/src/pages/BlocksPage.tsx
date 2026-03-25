import { useState } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { DataGrid, type GridColDef } from '@mui/x-data-grid';
import { useFetchGlobalBlocks } from '@/hooks/useFetchGlobalBlocks';
import { BlockDetailDrawer } from '@/components/blocks/BlockDetailDrawer';

const columns = (onView: (blockId: string, districtId: string) => void): GridColDef[] => [
    { field: 'name', headerName: 'Block Name', flex: 1 },
    { field: 'district_id', headerName: 'District ID', width: 280 },
    {
        field: 'avg_porosity', headerName: 'Avg Porosity', width: 130,
        valueFormatter: ({ value }) => value != null ? (value as number).toFixed(3) : '—',
    },
    {
        field: 'avg_permeability', headerName: 'Avg Permeability', width: 150,
        valueFormatter: ({ value }) => value != null ? (value as number).toFixed(3) : '—',
    },
    {
        field: 'created_at', headerName: 'Created At', width: 150,
        valueFormatter: ({ value }) => value ? new Date(value as string).toLocaleDateString() : '—',
    },
    {
        field: 'view', headerName: '', width: 80,
        renderCell: ({ row }) => (
            <Button size="small" onClick={() => onView(row.id, row.district_id)}>View</Button>
        ),
    },
];

const BlocksPage: React.FC = () => {
    const [paginationModel, setPaginationModel] = useState({ page: 0, pageSize: 25 });
    const [viewData, setViewData] = useState<{ id: string; districtId: string } | null>(null);
    const { data: blocks = [], isLoading } = useFetchGlobalBlocks(
        paginationModel.page * paginationModel.pageSize,
        paginationModel.pageSize
    );

    const rowCount = blocks.length === paginationModel.pageSize ? -1 : paginationModel.page * paginationModel.pageSize + blocks.length;

    return (
        <Box>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
                <Typography variant="h5" fontWeight={700}>Blocks</Typography>
            </Box>

            <DataGrid
                rows={blocks}
                columns={columns((id, districtId) => setViewData({ id, districtId }))}
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

            <BlockDetailDrawer 
                blockId={viewData?.id || null} 
                districtId={viewData?.districtId || null} 
                onClose={() => setViewData(null)} 
            />
        </Box>
    );
};

export default BlocksPage;
