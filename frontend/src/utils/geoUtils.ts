// @ts-nocheck – Turf.js has bundler-incompatible ESM export maps in v6; suppress at module level
import * as turf from '@turf/turf';
import type { GeoJSON } from 'geojson';

/**
 * Simplify a GeoJSON feature collection to reduce size.
 * @param geojson  The input GeoJSON
 * @param tolerance  Tolerance in degrees (default 0.001 ≈ 100m)
 */
export const simplifyGeoJSON = <T extends GeoJSON>(geojson: T, tolerance = 0.001): T =>
    turf.simplify(geojson as turf.AllGeoJSON, { tolerance, highQuality: false }) as unknown as T;

/**
 * Create a circular buffer polygon around a GeoJSON Point.
 * @param point  GeoJSON Point feature
 * @param radiusKm  Radius in kilometres
 */
export const bufferPoint = (point: turf.Feature<turf.Point>, radiusKm: number): turf.Feature<turf.Polygon> =>
    turf.buffer(point, radiusKm, { units: 'kilometers' }) as turf.Feature<turf.Polygon>;

/**
 * Check whether two GeoJSON features intersect spatially.
 */
export const doesIntersect = (a: turf.Feature, b: turf.Feature): boolean =>
    turf.booleanIntersects(a, b);

/**
 * Calculate approximate area in km² from an affected_area field (m²).
 */
export const metersSquaredToKm2 = (m2: number): number => m2 / 1_000_000;

/**
 * Format a vulnerability index (0–1) as a colour for MUI Chip.
 */
export const vulnerabilityColor = (
    index: number | null
): 'success' | 'warning' | 'error' | 'default' => {
    if (index == null) return 'default';
    if (index < 0.33) return 'success';
    if (index < 0.66) return 'warning';
    return 'error';
};
