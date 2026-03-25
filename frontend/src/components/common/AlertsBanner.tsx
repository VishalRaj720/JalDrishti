import React, { useState } from 'react';
import { Box, Alert, AlertTitle, Collapse, IconButton } from '@mui/material';
import { CloseOutlined } from '@mui/icons-material';
import type { Alert as AlertType } from '@/hooks/useAlerts';

interface Props {
    alerts: AlertType[];
}

export const AlertsBanner: React.FC<Props> = ({ alerts }) => {
    const [dismissed, setDismissed] = useState<Set<string>>(new Set());

    const activeAlerts = alerts.filter(a => !dismissed.has(a.id));

    if (activeAlerts.length === 0) return null;

    return (
        <Box sx={{ mb: 3, display: 'flex', flexDirection: 'column', gap: 1 }}>
            {activeAlerts.slice(0, 3).map(alert => (
                <Collapse in={true} key={alert.id}>
                    <Alert
                        severity={alert.severity}
                        action={
                            <IconButton
                                aria-label="close"
                                color="inherit"
                                size="small"
                                onClick={() => {
                                    setDismissed(prev => {
                                        const next = new Set(prev);
                                        next.add(alert.id);
                                        return next;
                                    });
                                }}
                            >
                                <CloseOutlined fontSize="inherit" />
                            </IconButton>
                        }
                    >
                        <AlertTitle>{alert.title}</AlertTitle>
                        {alert.message}
                    </Alert>
                </Collapse>
            ))}
        </Box>
    );
};
