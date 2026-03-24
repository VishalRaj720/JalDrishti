/** GeoJSON geometry types */
export type GeoJSONType =
    | 'Point'
    | 'LineString'
    | 'Polygon'
    | 'MultiPoint'
    | 'MultiLineString'
    | 'MultiPolygon'
    | 'GeometryCollection'
    | 'Feature'
    | 'FeatureCollection';

export interface GeoJSONGeometry {
    type: GeoJSONType;
    coordinates: unknown;
}

export interface GeoJSONFeature {
    type: 'Feature';
    geometry: GeoJSONGeometry;
    properties: Record<string, unknown>;
}

export interface GeoJSONFeatureCollection {
    type: 'FeatureCollection';
    features: GeoJSONFeature[];
}

/** Generic paginated API response */
export interface PaginatedResponse<T> {
    items: T[];
    total: number;
    page: number;
    size: number;
}

/** Standardised API error */
export interface ApiError {
    status: number;
    detail: string;
    errorCode?: string;
}

/** Error categories used by errorClassifier */
export type ErrorCategory =
    | 'DATA_INSUFFICIENT'
    | 'AUTH_ERROR'
    | 'NETWORK_ERROR'
    | 'VALIDATION_ERROR'
    | 'UNKNOWN';
