import React from 'react';
import { GeoJSON as LeafletGeoJSON } from 'react-leaflet';
import { useMapContext } from '@/contexts/MapContext';

export const BlockLayer: React.FC = React.memo(() => {
    const { layers } = useMapContext();
    
    if (!layers.blocks.visible || !layers.blocks.data) return null;

    return (
        <LeafletGeoJSON
            key={`blocks-${layers.blocks.data.features?.length}`}
            data={layers.blocks.data}
            style={{
                color: '#2dd4bf',
                weight: 2,
                opacity: 0.9,
                fillOpacity: 0.15,
            }}
        />
    );
});
