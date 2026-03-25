import { lazy, Suspense } from 'react';
import { Box, Paper } from '@mui/material';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import type { Map as LeafletMap } from 'leaflet';
import { useMapContext } from '@/contexts/MapContext';
import { DistrictLayer } from './layers/DistrictLayer';
import { BlockLayer } from './layers/BlockLayer';
import { AquiferLayer } from './layers/AquiferLayer';
import { IsrPointLayer } from './layers/IsrPointLayer';
import { PlumeLayer } from './layers/PlumeLayer';
import { IsrPointDetailDrawer } from '../isr/IsrPointDetailDrawer';

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
    const { mapRef } = useMapContext();

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

                <DistrictLayer />
                <BlockLayer />
                <AquiferLayer />
                <IsrPointLayer />
                <PlumeLayer />
            </MapContainer>
            <IsrPointDetailDrawer />
        </Paper>
    );
};

export default MapView;
