import React, { Component, type ErrorInfo, type ReactNode } from 'react';
import { Box, Typography, Button, Alert } from '@mui/material';

interface Props { children: ReactNode; fallback?: ReactNode; }
interface State { hasError: boolean; error: Error | null; }

class ErrorBoundary extends Component<Props, State> {
    state: State = { hasError: false, error: null };

    static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error('[ErrorBoundary]', error, info);
    }

    handleReset = () => this.setState({ hasError: false, error: null });

    render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;
            return (
                <Box sx={{ p: 4, display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'flex-start' }}>
                    <Alert severity="error" sx={{ width: '100%' }}>
                        <Typography fontWeight={600}>Something went wrong</Typography>
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                            {this.state.error?.message}
                        </Typography>
                    </Alert>
                    <Button variant="outlined" onClick={this.handleReset}>
                        Try Again
                    </Button>
                </Box>
            );
        }
        return this.props.children;
    }
}

export default ErrorBoundary;
