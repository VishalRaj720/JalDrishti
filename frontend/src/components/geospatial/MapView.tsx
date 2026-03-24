import { lazy, Suspense } from 'react';
import { Box, Paper } from '@mui/material';
import { MapContainer, TileLayer, GeoJSON as LeafletGeoJSON, useMap } from 'react-leaflet';
import type { Map as LeafletMap } from 'leaflet';
import { useMapContext } from '@/contexts/MapContext';
import LoadingSpinner from '@/components/common/LoadingSpinner';

interface MapRefCapture {
    mapRef: React.MutableRefObject<LeafletMap | null>;
}

const MapRefCapturer: React.FC<MapRefCapture> = ({ mapRef }) => {
    const map = useMap();
    mapRef.current = map;
    return null;
};

interface Props {
    height?: string | number;
}

const MapView: React.FC<Props> = ({ height = '500px' }) => {
    const { layers, mapRef } = useMapContext();

    const layerColors: Record<string, string> = {
        districts: '#38bdf8',
        blocks: '#2dd4bf',
        aquifers: '#a78bfa',
        isr_points: '#fb923c',
        plumes: '#f87171',
    };

    return (
        <Paper
            elevation={0}
            sx={{
                height,
                borderRadius: 2,
                overflow: 'hidden',
                border: '1px solid',
                borderColor: 'divider',
            }}
        >
            <MapContainer
                center={[23.6, 85.5]}   // Jharkhand center
                zoom={7}
                style={{ height: '100%', width: '100%' }}
                zoomControl
            >
                <MapRefCapturer mapRef={mapRef} />

                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; <a href="https://carto.com/">CARTO</a>'
                    maxZoom={19}
                />

                {Object.entries(layers).map(([key, layerState]) => {
                    if (!layerState.visible || !layerState.data) return null;
                    return (
                        <LeafletGeoJSON
                            key={key}
                            data={layerState.data}
                            style={{
                                color: layerColors[key] ?? '#38bdf8',
                                weight: 2,
                                opacity: 0.9,
                                fillOpacity: 0.15,
                            }}
                        />
                    );
                })}
            </MapContainer>
        </Paper>
    );
};

export default MapView;
