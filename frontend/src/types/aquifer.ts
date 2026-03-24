import type { GeoJSONGeometry } from './common';

export type AquiferType = 'unconfined' | 'confined' | 'semi_confined' | 'perched';

export interface Aquifer {
    id: string;
    name: string;
    type: AquiferType;
    block_id: string | null;
    min_depth: number | null;
    max_depth: number | null;
    thickness: number | null;        // computed on backend
    porosity: number | null;
    hydraulic_conductivity: number | null;
    transmissivity: number | null;
    storage_coefficient: number | null;
    specific_yield: number | null;
    quality_ec: number | null;
    dtw_decadal_avg: number | null;
    fractures_encountered: string | null;
    yield_range: string | null;
    geometry: GeoJSONGeometry | null;
    created_at: string;
    updated_at: string;
}

export interface AquiferCreate {
    name: string;
    type: AquiferType;
    block_id?: string;
    min_depth?: number;
    max_depth?: number;
    porosity?: number;
    hydraulic_conductivity?: number;
    transmissivity?: number;
    storage_coefficient?: number;
    specific_yield?: number;
    quality_ec?: number;
    dtw_decadal_avg?: number;
    fractures_encountered?: string;
    yield_range?: string;
    geometry?: GeoJSONGeometry;
}

export interface AquiferUpdate extends Partial<AquiferCreate> { }
