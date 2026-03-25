import React, { useCallback } from 'react';
import { GeoJSON as LeafletGeoJSON } from 'react-leaflet';
import { useQuery } from '@tanstack/react-query';
import axiosInstance from '@/api/axiosInstance';
import type { Layer as LLayer, Path } from 'leaflet';
import { useMapContext } from '@/contexts/MapContext';

export const DistrictLayer: React.FC = React.memo(() => {
    const { layers } = useMapContext();
    if (!layers.districts.visible) return null;

    const { data } = useQuery({
        queryKey: ['districts', 'geojson'],
        queryFn: () => axiosInstance.get('/districts/geojson').then(r => r.data),
        staleTime: 10 * 60 * 1000,
        gcTime: 30 * 60 * 1000,
    });

    const style = useCallback((feature: any) => {
        const vi = feature.properties.vulnerability_index ?? 0;
        return {
            color: vi > 0.66 ? '#f87171' : vi > 0.33 ? '#fbbf24' : '#34d399',
            weight: 1.5,
            fillOpacity: 0.25 + (vi * 0.3),  // more opaque = higher risk
        };
    }, []);

    const onEachFeature = useCallback((feature: any, layer: LLayer) => {
        layer.bindPopup(`
            <b>${feature.properties.name}</b><br/>
            Vulnerability: ${(feature.properties.vulnerability_index ?? 0).toFixed(2)}<br/>
            Avg Porosity: ${feature.properties.avg_porosity?.toFixed(3) ?? '—'}
        `);
        (layer as Path).on('mouseover', (e: any) => e.target.setStyle({ fillOpacity: 0.6 }));
        (layer as Path).on('mouseout', (e: any) => e.target.setStyle(style(feature)));
    }, [style]);

    if (!data) return null;

    return <LeafletGeoJSON key={data.features?.length} data={data} style={style} onEachFeature={onEachFeature} />;
});
