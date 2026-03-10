export const ZOOM_AGG_MAX = 12;
export const ZOOM_CLUSTER_MAX = 15;
export const ZOOM_POINT_MIN = 16;

export function getZoomTier(zoom) {
  if (zoom <= ZOOM_AGG_MAX) return "aggregate";
  if (zoom <= ZOOM_CLUSTER_MAX) return "cluster";
  return "point";
}
