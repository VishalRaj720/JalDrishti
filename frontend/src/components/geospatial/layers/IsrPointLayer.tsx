import React from 'react';
import { CircleMarker, Popup, Tooltip } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import { useNavigate } from 'react-router-dom';
import { useFetchIsrPoints } from '@/hooks/useFetchIsrPoints';
import { useMapContext } from '@/contexts/MapContext';

export const IsrPointLayer: React.FC = React.memo(() => {
    const { layers, setSelectedIsrId } = useMapContext();
    const { data: isrPoints = [] } = useFetchIsrPoints();
    const navigate = useNavigate();
    
    if (!layers.isr_points.visible) return null;

    return (
        <MarkerClusterGroup chunkedLoading maxClusterRadius={60}>
            {isrPoints.map(isr => {
                if (!isr.location?.coordinates) return null;
                const [lon, lat] = isr.location.coordinates as [number, number];
                
                const isActive = isr.injection_start_date && 
                    (!isr.injection_end_date || new Date(isr.injection_end_date) > new Date());

                return (
                    <CircleMarker
                        key={isr.id}
                        center={[lat, lon]}
                        radius={isActive ? 10 : 6}
                        pathOptions={{
                            color: isActive ? '#f87171' : '#fb923c',
                            fillColor: isActive ? '#fca5a5' : '#fed7aa',
                            fillOpacity: 0.8,
                            weight: 2,
                        }}
                        eventHandlers={{
                            click: () => {
                                setSelectedIsrId(isr.id);
                                navigate(`/isr-points?selected=${isr.id}`);
                            },
                        }}
                    >
                        <Popup>
                            <b>{isr.name}</b><br/>
                            Rate: {isr.injection_rate ?? '—'} m³/day<br/>
                            Status: {isActive ? '🔴 Active' : '⚪ Inactive'}<br/>
                            <button onClick={() => navigate('/isr-points')} style={{ marginTop: '8px', cursor: 'pointer' }}>
                                View Details
                            </button>
                        </Popup>
                        <Tooltip>{isr.name}</Tooltip>
                    </CircleMarker>
                );
            })}
        </MarkerClusterGroup>
    );
});
