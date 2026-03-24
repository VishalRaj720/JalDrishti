import { ApiError, type ErrorCategory } from '@/types/common';

const HTTP_TO_CATEGORY: Record<number, ErrorCategory> = {
    400: 'VALIDATION_ERROR',
    401: 'AUTH_ERROR',
    403: 'AUTH_ERROR',
    422: 'VALIDATION_ERROR',
    503: 'NETWORK_ERROR',
};

export const classifyError = (error: unknown): ErrorCategory => {
    if (error && typeof error === 'object') {
        const e = error as { status?: number; detail?: string };
        if (e.status && HTTP_TO_CATEGORY[e.status]) {
            return HTTP_TO_CATEGORY[e.status];
        }
        const detail = e.detail?.toLowerCase() ?? '';
        if (
            detail.includes('insufficient') ||
            detail.includes('missing') ||
            detail.includes('no data')
        ) {
            return 'DATA_INSUFFICIENT';
        }
    }
    if (!navigator.onLine) return 'NETWORK_ERROR';
    return 'UNKNOWN';
};

export const getUserFriendlyMessage = (category: ErrorCategory): string => {
    switch (category) {
        case 'DATA_INSUFFICIENT':
            return 'Simulation data is insufficient. Please ingest piezometric or hydraulic data first.';
        case 'AUTH_ERROR':
            return 'Your session has expired. Please log in again.';
        case 'NETWORK_ERROR':
            return 'Network error. Please check your connection.';
        case 'VALIDATION_ERROR':
            return 'Validation failed. Please check your inputs.';
        default:
            return 'An unexpected error occurred. Please try again.';
    }
};
