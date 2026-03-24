import { createTheme } from '@mui/material/styles';

const theme = createTheme({
    palette: {
        mode: 'dark',
        primary: {
            main: '#38bdf8',    // sky-400
            light: '#7dd3fc',
            dark: '#0369a1',
        },
        secondary: {
            main: '#2dd4bf',    // teal-400
            light: '#5eead4',
            dark: '#0f766e',
        },
        background: {
            default: '#0a1628',
            paper: '#111e35',
        },
        error: { main: '#f87171' },
        warning: { main: '#fbbf24' },
        success: { main: '#34d399' },
        text: {
            primary: '#e2e8f0',
            secondary: '#94a3b8',
        },
        divider: 'rgba(255,255,255,0.08)',
    },
    typography: {
        fontFamily: '"Outfit", "Inter", "Roboto", sans-serif',
        h1: { fontWeight: 700, letterSpacing: '-0.02em' },
        h2: { fontWeight: 700 },
        h3: { fontWeight: 600 },
        h4: { fontWeight: 600 },
        h5: { fontWeight: 600 },
        h6: { fontWeight: 600 },
        button: { textTransform: 'none', fontWeight: 600 },
    },
    shape: { borderRadius: 10 },
    components: {
        MuiButton: {
            styleOverrides: {
                root: {
                    borderRadius: 8,
                    boxShadow: 'none',
                    '&:hover': { boxShadow: '0 4px 20px rgba(56,189,248,0.25)' },
                },
            },
        },
        MuiCard: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                    border: '1px solid rgba(255,255,255,0.07)',
                    backdropFilter: 'blur(12px)',
                },
            },
        },
        MuiPaper: {
            styleOverrides: {
                root: {
                    backgroundImage: 'none',
                    border: '1px solid rgba(255,255,255,0.06)',
                },
            },
        },
        MuiTableCell: {
            styleOverrides: {
                head: { color: '#94a3b8', fontWeight: 600, fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: '0.05em' },
            },
        },
        MuiChip: {
            styleOverrides: {
                root: { borderRadius: 6 },
            },
        },
        MuiTextField: {
            defaultProps: { variant: 'outlined', size: 'small' },
        },
        MuiDrawer: {
            styleOverrides: {
                paper: {
                    border: 'none',
                    borderRight: '1px solid rgba(255,255,255,0.06)',
                    background: '#0d1b2e',
                },
            },
        },
    },
});

export default theme;
