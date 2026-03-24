import React, { createContext, useContext, useState, useRef, useCallback } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import type { GeoJSONFeatureCollection } from '@/types/common';

export type LayerKey = 'districts' | 'blocks' | 'aquifers' | 'isr_points' | 'plumes';

export interface LayerState {
    visible: boolean;
    data: GeoJSONFeatureCollection | null;
}

export type LayersMap = Record<LayerKey, LayerState>;

interface MapContextValue {
    layers: LayersMap;
    mapRef: React.MutableRefObject<LeafletMap | null>;
    setLayerVisible: (key: LayerKey, visible: boolean) => void;
    updateLayerData: (key: LayerKey, data: GeoJSONFeatureCollection | null) => void;
    selectedIsrId: string | null;
    setSelectedIsrId: (id: string | null) => void;
}

const defaultLayers: LayersMap = {
    districts: { visible: true, data: null },
    blocks: { visible: true, data: null },
    aquifers: { visible: true, data: null },
    isr_points: { visible: true, data: null },
    plumes: { visible: true, data: null },
};

const MapContext = createContext<MapContextValue | null>(null);

export const MapProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [layers, setLayers] = useState<LayersMap>(defaultLayers);
    const [selectedIsrId, setSelectedIsrId] = useState<string | null>(null);
    const mapRef = useRef<LeafletMap | null>(null);

    const setLayerVisible = useCallback((key: LayerKey, visible: boolean) => {
        setLayers((prev) => ({
            ...prev,
            [key]: { ...prev[key], visible },
        }));
    }, []);

    const updateLayerData = useCallback(
        (key: LayerKey, data: GeoJSONFeatureCollection | null) => {
            setLayers((prev) => ({
                ...prev,
                [key]: { ...prev[key], data },
            }));
        },
        []
    );

    return (
        <MapContext.Provider
            value={{ layers, mapRef, setLayerVisible, updateLayerData, selectedIsrId, setSelectedIsrId }}
        >
            {children}
        </MapContext.Provider>
    );
};

export const useMapContext = (): MapContextValue => {
    const ctx = useContext(MapContext);
    if (!ctx) throw new Error('useMapContext must be used within a MapProvider');
    return ctx;
};
