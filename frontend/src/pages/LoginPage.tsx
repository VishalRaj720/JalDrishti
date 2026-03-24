import { useState } from 'react';
import {
    Box, Paper, Typography, TextField, Button, Alert,
    CircularProgress, InputAdornment, IconButton,
} from '@mui/material';
import { VisibilityOutlined, VisibilityOffOutlined } from '@mui/icons-material';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { classifyError, getUserFriendlyMessage } from '@/utils/errorClassifier';

const LoginPage: React.FC = () => {
    const { login } = useAuth();
    const navigate = useNavigate();
    const location = useLocation();
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname ?? '/dashboard';

    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [showPwd, setShowPwd] = useState(false);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setLoading(true);
        setError(null);
        try {
            await login(email, password);
            navigate(from, { replace: true });
        } catch (err) {
            const category = classifyError(err);
            setError(getUserFriendlyMessage(category));
        } finally {
            setLoading(false);
        }
    };

    return (
        <Box
            sx={{
                minHeight: '100vh',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                bgcolor: 'background.default',
                background: 'radial-gradient(ellipse at 20% 60%, rgba(56,189,248,0.08) 0%, transparent 60%), radial-gradient(ellipse at 80% 20%, rgba(45,212,191,0.06) 0%, transparent 60%)',
                p: 2,
            }}
        >
            <Paper sx={{ p: 4, width: '100%', maxWidth: 420 }}>
                <Box textAlign="center" mb={3}>
                    <Typography variant="h4" fontWeight={700} color="primary.main">💧 JalDrishti</Typography>
                    <Typography variant="body2" color="text.secondary" mt={0.5}>
                        Groundwater Intelligence Platform
                    </Typography>
                </Box>

                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

                <form onSubmit={handleSubmit}>
                    <TextField
                        id="email" fullWidth label="Email" type="email"
                        value={email} onChange={(e) => setEmail(e.target.value)}
                        required autoFocus sx={{ mb: 2 }}
                    />
                    <TextField
                        id="password" fullWidth label="Password"
                        type={showPwd ? 'text' : 'password'}
                        value={password} onChange={(e) => setPassword(e.target.value)}
                        required sx={{ mb: 3 }}
                        InputProps={{
                            endAdornment: (
                                <InputAdornment position="end">
                                    <IconButton onClick={() => setShowPwd(!showPwd)} edge="end" aria-label="Toggle password visibility">
                                        {showPwd ? <VisibilityOffOutlined /> : <VisibilityOutlined />}
                                    </IconButton>
                                </InputAdornment>
                            ),
                        }}
                    />
                    <Button
                        id="login-btn" type="submit" fullWidth variant="contained"
                        size="large" disabled={loading}
                        startIcon={loading ? <CircularProgress size={18} /> : undefined}
                    >
                        {loading ? 'Signing in…' : 'Sign In'}
                    </Button>
                </form>
            </Paper>
        </Box>
    );
};

export default LoginPage;
