import type { GeoJSONGeometry } from './common';

export type SimulationStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface IsrPoint {
    id: string;
    name: string;
    injection_rate: number | null;
    injection_start_date: string | null;
    injection_end_date: string | null;
    location: GeoJSONGeometry | null;     // GeoJSON Point
    created_at: string;
    updated_at: string;
}

export interface IsrPointCreate {
    name: string;
    injection_rate?: number;
    injection_start_date?: string;
    injection_end_date?: string;
    location?: GeoJSONGeometry;
}

export interface IsrPointUpdate extends Partial<IsrPointCreate> { }

export interface PlumeParameters {
    dispersivity_longitudinal?: number;
    dispersivity_transverse?: number;
    retardation_factor?: number;
    decay_constant?: number;
}

export interface VulnerabilityAssessment {
    risk_score: number;
    risk_level: 'low' | 'moderate' | 'high' | 'critical';
    confidence: number;
    model_version: string;
    factors: Record<string, number>;
}

export interface ConcentrationSpread {
    geometry: GeoJSONGeometry; // Polygon / MultiPolygon plume
    time_steps: number[];
    concentrations: number[];
    hydraulic_gradient?: number[];
    uranium?: {
        max: number;
        exceeds_limit: boolean;
        who_limit: number;
        unit: string;
    };
    [key: string]: any;
}

export interface Simulation {
    id: string;
    isr_point_id: string;
    simulation_date: string;
    status: SimulationStatus;
    task_id: string | null;
    affected_area: number | null;
    estimated_concentration_spread: ConcentrationSpread | null;
    vulnerability_assessment: VulnerabilityAssessment | null;
    uncertainty_estimate: number | null;
    suggested_recovery: string | null;
    error_message: string | null;
    created_at: string;
    // Audit info (extended from backend in future)
    run_by?: string;
    model_version?: string;
}

export interface SimulationRunRequest {
    plume_parameters?: PlumeParameters;
}

/** WebSocket event payload */
export interface SimulationCompleteEvent {
    simulation_id: string;
    status: SimulationStatus;
    result: Partial<Simulation>;
}
