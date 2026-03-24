import {
    Dialog, DialogTitle, DialogContent, DialogContentText,
    DialogActions, Button,
} from '@mui/material';

interface Props {
    open: boolean;
    title?: string;
    message: string;
    confirmLabel?: string;
    onConfirm: () => void;
    onCancel: () => void;
    loading?: boolean;
}

export const ConfirmDialog: React.FC<Props> = ({
    open, title = 'Confirm action', message,
    confirmLabel = 'Delete', onConfirm, onCancel, loading,
}) => (
    <Dialog open={open} onClose={onCancel} maxWidth="xs" fullWidth>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
            <DialogContentText>{message}</DialogContentText>
        </DialogContent>
        <DialogActions>
            <Button onClick={onCancel} color="inherit" disabled={loading}>Cancel</Button>
            <Button onClick={onConfirm} color="error" variant="contained" disabled={loading}>
                {confirmLabel}
            </Button>
        </DialogActions>
    </Dialog>
);
