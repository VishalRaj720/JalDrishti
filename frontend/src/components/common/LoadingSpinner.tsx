import { Box, CircularProgress } from '@mui/material';

interface Props {
    fullPage?: boolean;
    size?: number;
}

const LoadingSpinner: React.FC<Props> = ({ fullPage = false, size = 40 }) => {
    if (fullPage) {
        return (
            <Box
                sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    height: '100vh',
                    bgcolor: 'background.default',
                }}
            >
                <CircularProgress size={size} />
            </Box>
        );
    }
    return (
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', p: 4 }}>
            <CircularProgress size={size} />
        </Box>
    );
};

export default LoadingSpinner;
