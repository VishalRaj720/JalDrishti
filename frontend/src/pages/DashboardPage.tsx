import React from 'react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';

export const DashboardPage: React.FC = () => {
    const { user, logout } = useAuth();
    const navigate = useNavigate();

    const handleLogout = async () => {
        await logout();
        navigate('/login');
    };

    return (
        <div className="min-h-screen bg-gray-50">
            <nav className="bg-white shadow-sm">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                    <div className="flex justify-between h-16 items-center">
                        <h1 className="text-xl font-bold text-gray-900">
                            1st Month Project - Dashboard
                        </h1>
                        <button
                            onClick={handleLogout}
                            className="btn-secondary"
                        >
                            Logout
                        </button>
                    </div>
                </div>
            </nav>

            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
                <div className="card">
                    <h2 className="text-2xl font-bold text-gray-900 mb-6">
                        Welcome, {user?.name}!
                    </h2>

                    <div className="space-y-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div className="bg-blue-50 p-4 rounded-lg">
                                <h3 className="font-semibold text-gray-700 mb-2">Email</h3>
                                <p className="text-gray-900">{user?.email}</p>
                            </div>

                            <div className="bg-green-50 p-4 rounded-lg">
                                <h3 className="font-semibold text-gray-700 mb-2">Role</h3>
                                <p className="text-gray-900 capitalize">{user?.role}</p>
                            </div>

                            <div className="bg-purple-50 p-4 rounded-lg">
                                <h3 className="font-semibold text-gray-700 mb-2">User ID</h3>
                                <p className="text-gray-900 font-mono text-sm">{user?.id}</p>
                            </div>

                            <div className="bg-yellow-50 p-4 rounded-lg">
                                <h3 className="font-semibold text-gray-700 mb-2">Status</h3>
                                <p className="text-green-600 font-semibold">✓ Authenticated</p>
                            </div>
                        </div>

                        <div className="mt-8 p-6 bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg border border-blue-200">
                            <h3 className="text-lg font-semibold text-gray-900 mb-3">
                                🎉 1st Month Scope Completed
                            </h3>
                            <p className="text-gray-700 mb-2">
                                This project demonstrates the following features:
                            </p>
                            <ul className="list-disc list-inside space-y-1 text-gray-700">
                                <li>User database entity with 3 roles (Admin, Analyst, Viewer)</li>
                                <li>JWT-based authentication system</li>
                                <li>Login UI with role-based access</li>
                                <li>Protected dashboard route</li>
                                <li>Token refresh mechanism</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </main>
        </div>
    );
};
