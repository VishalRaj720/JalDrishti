declare module 'react-leaflet-cluster' {
    import { ComponentType, ReactNode } from 'react';
    import { MarkerClusterGroupOptions } from 'leaflet';

    export interface MarkerClusterGroupProps extends MarkerClusterGroupOptions {
        children: ReactNode;
        chunkedLoading?: boolean;
        maxClusterRadius?: number;
    }

    const MarkerClusterGroup: ComponentType<MarkerClusterGroupProps>;
    export default MarkerClusterGroup;
}
