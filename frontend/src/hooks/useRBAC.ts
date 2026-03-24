import { useAuth } from './useAuth';
import type { UserRole } from '@/types/user';

export const useRBAC = () => {
    const { role } = useAuth();

    const hasRole = (...allowedRoles: UserRole[]): boolean =>
        role != null && allowedRoles.includes(role);

    return {
        isAdmin: hasRole('admin'),
        isAnalyst: hasRole('analyst'),
        isViewer: hasRole('viewer'),
        isAnalystOrAdmin: hasRole('admin', 'analyst'),
        canCreateEdit: hasRole('admin', 'analyst'),
        canDelete: hasRole('admin'),
    };
};
