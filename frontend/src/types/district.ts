import type { GeoJSONGeometry } from './common';

export interface District {
    id: string;
    name: string;
    avg_porosity: number | null;
    avg_hydraulic_conductivity: number | null;
    vulnerability_index: number | null;
    geometry: GeoJSONGeometry | null;
    created_at: string;
    updated_at: string;
}

export interface DistrictCreate {
    name: string;
    avg_porosity?: number;
    avg_hydraulic_conductivity?: number;
    vulnerability_index?: number;
    geometry?: GeoJSONGeometry;
}

export interface DistrictUpdate extends Partial<DistrictCreate> { }

export interface Block {
    id: string;
    name: string;
    district_id: string;
    aquifer_distribution: Record<string, number> | null;
    avg_porosity: number | null;
    avg_permeability: number | null;
    geometry: GeoJSONGeometry | null;
    created_at: string;
    updated_at: string;
}

export interface BlockCreate {
    name: string;
    district_id: string;
    aquifer_distribution?: Record<string, number>;
    avg_porosity?: number;
    avg_permeability?: number;
    geometry?: GeoJSONGeometry;
}

export interface BlockUpdate extends Partial<Omit<BlockCreate, 'district_id'>> { }
