import React, { lazy, Suspense } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { MainLayout } from '@/components/layout/MainLayout';
import LoadingSpinner from '@/components/common/LoadingSpinner';

// Lazy-loaded pages for code splitting
const LoginPage = lazy(() => import('@/pages/LoginPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const DistrictsPage = lazy(() => import('@/pages/DistrictsPage'));
const AquifersPage = lazy(() => import('@/pages/AquifersPage'));
const IsrPointsPage = lazy(() => import('@/pages/IsrPointsPage'));
const SimulationDetailPage = lazy(() => import('@/pages/SimulationDetailPage'));

export const AppRoutes: React.FC = () => {
    return (
        <Suspense fallback={<LoadingSpinner fullPage />}>
            <Routes>
                {/* Public */}
                <Route path="/login" element={<LoginPage />} />

                {/* Protected – all roles */}
                <Route
                    element={
                        <ProtectedRoute>
                            <MainLayout />
                        </ProtectedRoute>
                    }
                >
                    <Route path="/dashboard" element={<DashboardPage />} />
                    <Route path="/districts" element={<DistrictsPage />} />
                    <Route path="/aquifers" element={<AquifersPage />} />
                    <Route
                        path="/simulations/:id"
                        element={<SimulationDetailPage />}
                    />

                    {/* Analyst + Admin only */}
                    <Route
                        path="/isr-points"
                        element={
                            <ProtectedRoute allowedRoles={['admin', 'analyst']}>
                                <IsrPointsPage />
                            </ProtectedRoute>
                        }
                    />
                </Route>

                {/* Redirects */}
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
        </Suspense>
    );
};
