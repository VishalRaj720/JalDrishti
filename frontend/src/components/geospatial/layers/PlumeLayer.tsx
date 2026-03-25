import React from 'react';
import { GeoJSON as LeafletGeoJSON, Popup } from 'react-leaflet';
import { useSelector } from 'react-redux';
import { selectAllSimulations } from '@/redux/slices/simulationsSlice';
import { useMapContext } from '@/contexts/MapContext';

export const PlumeLayer: React.FC = React.memo(() => {
    const { layers } = useMapContext();
    const simulations = useSelector(selectAllSimulations);
    
    if (!layers.plumes.visible) return null;

    const completedWithPlume = simulations.filter(
        s => s.status === 'completed' && s.estimated_concentration_spread?.geometry
    );

    return (
        <>
            {completedWithPlume.map(sim => {
                const uraniumObj = sim.estimated_concentration_spread?.uranium;
                const uraniumMax = uraniumObj?.max;
                const exceedsLimit = uraniumObj?.exceeds_limit;
                
                return (
                    <LeafletGeoJSON
                        key={sim.id}
                        data={sim.estimated_concentration_spread?.geometry as any}
                        style={{
                            color: exceedsLimit ? '#ef4444' : '#f97316',
                            fillOpacity: 0.3,
                            weight: 2,
                            dashArray: '5,3',
                        }}
                    >
                        <Popup>
                            <b>Simulation {sim.id.substring(0, 8)}</b><br/>
                            Uranium: {uraniumMax ?? '—'} mg/L<br/>
                            WHO Limit: 0.03 mg/L<br/>
                            {exceedsLimit && <b style={{color:'red'}}>⚠ EXCEEDS LIMIT</b>}
                        </Popup>
                    </LeafletGeoJSON>
                );
            })}
        </>
    );
});
