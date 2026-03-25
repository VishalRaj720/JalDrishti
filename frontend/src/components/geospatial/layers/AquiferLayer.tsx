import React from 'react';
import { GeoJSON as LeafletGeoJSON } from 'react-leaflet';
import { useMapContext } from '@/contexts/MapContext';

export const AquiferLayer: React.FC = React.memo(() => {
    const { layers } = useMapContext();
    
    if (!layers.aquifers.visible || !layers.aquifers.data) return null;

    return (
        <LeafletGeoJSON
            key={`aquifers-${layers.aquifers.data.features?.length}`}
            data={layers.aquifers.data}
            style={{
                color: '#a78bfa',
                weight: 2,
                opacity: 0.9,
                fillOpacity: 0.15,
            }}
            onEachFeature={(feature, layer) => {
                if (feature.properties?.name) {
                    layer.bindPopup(`<b>${feature.properties.name}</b><br/>Type: ${feature.properties.type ?? '—'}`);
                }
            }}
        />
    );
});
