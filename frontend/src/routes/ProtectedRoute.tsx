import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useSelector } from 'react-redux';
import { selectIsAuthenticated, selectUserRole, selectIsInitialized } from '@/redux/slices/authSlice';
import type { UserRole } from '@/types/user';
import LoadingSpinner from '@/components/common/LoadingSpinner';

interface Props {
    children: React.ReactNode;
    allowedRoles?: UserRole[];
}

export const ProtectedRoute: React.FC<Props> = ({ children, allowedRoles }) => {
    const isAuthenticated = useSelector(selectIsAuthenticated);
    const role = useSelector(selectUserRole);
    const isInitialized = useSelector(selectIsInitialized);
    const location = useLocation();

    if (!isInitialized) {
        return <LoadingSpinner fullPage />;
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    if (allowedRoles && role && !allowedRoles.includes(role)) {
        return <Navigate to="/dashboard" replace />;
    }

    return <>{children}</>;
};
