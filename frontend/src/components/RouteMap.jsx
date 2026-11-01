import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { animate } from 'motion'
import { useEffect, useMemo, useRef, useState } from 'react'
import {
  averageLatitude,
  boundsOfRoutes,
  checkpointPopupHtml,
  checkpointsGeoJson,
  corridorGeoJson,
  HEATMAP_INTENSITY,
  heatmapRadiusExpression,
  heatmapWeightExpression,
  riskGradientExpression,
  routeLinesGeoJson,
} from '../mapData'
import { RISK_COLORS } from '../risk'
import { cumulativeDistances, pointAlongPath, truckProgress } from '../timeline'
import TripTimeline from './TripTimeline'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN
const CONTINENTAL_US = { center: [-98.5, 39.5], zoom: 3.4 }
const EMPTY_COLLECTION = { type: 'FeatureCollection', features: [] }
const SLATE = '#7C8B96'

const TRUCK_GLIDE_SECONDS = 0.35

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

function createTruckElement() {
  const element = document.createElement('div')
  element.className = 'truck-marker'
  element.setAttribute('aria-hidden', 'true')
  element.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" ' +
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 7h11v9H2z"/>' +
    '<path d="M13 10h4l3 3v3h-7z"/><circle cx="6" cy="17.5" r="1.5"/><circle cx="16.5" cy="17.5" r="1.5"/></svg>'
  return element
}

function withAlpha(hex, alpha) {
  const value = parseInt(hex.slice(1), 16)
  return `rgba(${value >> 16}, ${(value >> 8) & 255}, ${value & 255}, ${alpha})`
}

// Density 0-1 follows the 0-4 scale: 0.25 Moderate ... 1 No Travel. Low stays
// clear so the base map shows through wherever conditions are fine.
const HEATMAP_COLOR = [
  'interpolate', ['linear'], ['heatmap-density'],
  0, withAlpha(RISK_COLORS.moderate, 0),
  0.25, withAlpha(RISK_COLORS.moderate, 0.45),
  0.5, withAlpha(RISK_COLORS.high, 0.6),
  0.75, withAlpha(RISK_COLORS.severe, 0.7),
  1, withAlpha(RISK_COLORS.no_travel, 0.8),
]

function addCorridorHeatmap(map) {
  map.addSource('corridor', { type: 'geojson', data: EMPTY_COLLECTION })
  // Under the place labels so town names stay readable through the heat.
  const firstLabelLayer = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id
  map.addLayer({
    id: 'corridor-heat',
    type: 'heatmap',
    source: 'corridor',
    paint: {
      'heatmap-weight': heatmapWeightExpression('risk', 0),
      'heatmap-color': HEATMAP_COLOR,
      'heatmap-intensity': HEATMAP_INTENSITY,
      'heatmap-opacity': 0.85,
    },
  }, firstLabelLayer)
}

function addRouteLayers(map) {
  map.addSource('routes', { type: 'geojson', data: EMPTY_COLLECTION })
  // lineMetrics enables line-progress, which the risk gradient is keyed on.
  map.addSource('selected-route', { type: 'geojson', data: EMPTY_COLLECTION, lineMetrics: true })
  map.addSource('checkpoints', { type: 'geojson', data: EMPTY_COLLECTION })

  map.addLayer({
    id: 'other-routes',
    type: 'line',
    source: 'routes',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': SLATE, 'line-width': 4, 'line-opacity': 0.75 },
  })
  map.addLayer({
    id: 'selected-route-casing',
    type: 'line',
    source: 'selected-route',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-color': '#FFFFFF', 'line-width': 9 },
  })
  map.addLayer({
    id: 'selected-route-risk',
    type: 'line',
    source: 'selected-route',
    layout: { 'line-join': 'round', 'line-cap': 'round' },
    paint: { 'line-width': 5, 'line-gradient': '#3E9B5F' },
  })
  map.addLayer({
    id: 'checkpoints',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 3.5, 9, 7],
      'circle-color': ['get', 'color'],
      'circle-stroke-color': '#FFFFFF',
      'circle-stroke-width': 1.5,
    },
  })
}

export default function RouteMap({ plan, selectedRouteId, onSelectRoute }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const popupRef = useRef(null)
  const truckMarkerRef = useRef(null)
  // Where the truck marker currently sits, as a share (0-1) of the selected route.
  const truckShareRef = useRef({ routeId: null, share: 0 })
  const [isMapReady, setIsMapReady] = useState(false)
  const [heatmapLayer, setHeatmapLayer] = useState('risk')
  const [forecastHour, setForecastHour] = useState(0)
  // A new plan starts the slider back at departure (adjusting state during render,
  // the React-recommended way to reset state when a prop changes).
  const [heatmapPlan, setHeatmapPlan] = useState(plan)
  if (plan !== heatmapPlan) {
    setHeatmapPlan(plan)
    setForecastHour(0)
  }
  // Map event handlers are registered once; this ref lets them see the latest props.
  const latest = useRef({ plan, selectedRouteId, onSelectRoute })
  useEffect(() => {
    latest.current = { plan, selectedRouteId, onSelectRoute }
  })

  useEffect(() => {
    if (!MAPBOX_TOKEN) return undefined
    mapboxgl.accessToken = MAPBOX_TOKEN
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: 'mapbox://styles/mapbox/light-v11',
      ...CONTINENTAL_US,
    })
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')
    popupRef.current = new mapboxgl.Popup({ closeButton: true, maxWidth: '260px' })
    truckMarkerRef.current = new mapboxgl.Marker({ element: createTruckElement() })

    map.on('load', () => {
      addCorridorHeatmap(map)
      addRouteLayers(map)
      setIsMapReady(true)
    })

    map.on('click', 'other-routes', (event) => {
      latest.current.onSelectRoute(event.features[0].properties.id)
    })

    map.on('click', 'checkpoints', (event) => {
      const { plan: currentPlan, selectedRouteId: routeId } = latest.current
      const route = currentPlan.routes.find((candidate) => candidate.id === routeId)
      const checkpoint = route.checkpoints[event.features[0].properties.sequence]
      const levelLabels = Object.fromEntries(currentPlan.risk_levels.map((level) => [level.key, level.label]))
      popupRef.current
        .setLngLat([checkpoint.lng, checkpoint.lat])
        .setHTML(checkpointPopupHtml(checkpoint, levelLabels, currentPlan.load_weight_lb))
        .addTo(map)
    })

    for (const layerId of ['other-routes', 'checkpoints']) {
      map.on('mouseenter', layerId, () => { map.getCanvas().style.cursor = 'pointer' })
      map.on('mouseleave', layerId, () => { map.getCanvas().style.cursor = '' })
    }

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
      setIsMapReady(false)
    }
  }, [])

  // New plan: draw every route and zoom to fit the trip.
  useEffect(() => {
    const map = mapRef.current
    if (!isMapReady || !plan) return
    map.getSource('routes').setData(routeLinesGeoJson(plan.routes))
    const corridor = plan.corridor_forecast
    map.getSource('corridor').setData(corridorGeoJson(corridor))
    map.setPaintProperty('corridor-heat', 'heatmap-radius',
      heatmapRadiusExpression(corridor.spacing_m, averageLatitude(corridor.points)))
    // The timeline docks under the map once a plan arrives, shrinking it.
    map.resize()
    map.fitBounds(boundsOfRoutes(plan.routes), { padding: 48, duration: 600 })
  }, [isMapReady, plan])

  // Selection: recolor the chosen route by risk and show its checkpoints.
  useEffect(() => {
    const map = mapRef.current
    if (!isMapReady || !plan) return
    const selected = plan.routes.find((route) => route.id === selectedRouteId)
    if (!selected) return
    popupRef.current.remove()
    map.setFilter('other-routes', ['!=', ['get', 'id'], selected.id])
    map.getSource('selected-route').setData(routeLinesGeoJson([selected]))
    map.setPaintProperty('selected-route-risk', 'line-gradient', riskGradientExpression(selected))
    map.getSource('checkpoints').setData(checkpointsGeoJson(selected))
  }, [isMapReady, plan, selectedRouteId])

  // Slider or layer change: point the heatmap at another property. No data reload.
  useEffect(() => {
    const map = mapRef.current
    if (!isMapReady) return
    const isOff = heatmapLayer === 'off'
    map.setLayoutProperty('corridor-heat', 'visibility', isOff ? 'none' : 'visible')
    if (!isOff) map.setPaintProperty('corridor-heat', 'heatmap-weight', heatmapWeightExpression(heatmapLayer, forecastHour))
  }, [isMapReady, heatmapLayer, forecastHour])

  const selectedRoute = plan?.routes.find((route) => route.id === selectedRouteId)
  // Path distances are needed on every slider step; measure each route once.
  const selectedPathDistances = useMemo(
    () => (selectedRoute ? cumulativeDistances(selectedRoute.path) : null),
    [selectedRoute],
  )

  // Truck marker: where the selected route's truck is at the timeline hour.
  // Motion glides it along the road between hours; a route switch jumps.
  useEffect(() => {
    const map = mapRef.current
    const marker = truckMarkerRef.current
    if (!isMapReady || !selectedRoute) return undefined
    const lastCheckpoint = selectedRoute.checkpoints[selectedRoute.checkpoints.length - 1]
    const moment = Date.parse(plan.corridor_forecast.hours[forecastHour])
    const { miles } = truckProgress(selectedRoute, moment)
    const targetShare = lastCheckpoint.distance_miles ? miles / lastCheckpoint.distance_miles : 0

    const placeAt = (share) => {
      truckShareRef.current = { routeId: selectedRoute.id, share }
      const [lat, lng] = pointAlongPath(selectedRoute.path, selectedPathDistances, share)
      marker.setLngLat([lng, lat])
    }
    if (!marker.getElement().isConnected) {
      placeAt(targetShare)
      marker.addTo(map)
      return undefined
    }
    const current = truckShareRef.current
    if (current.routeId !== selectedRoute.id || prefersReducedMotion()) {
      placeAt(targetShare)
      return undefined
    }
    const glide = animate(current.share, targetShare, {
      duration: TRUCK_GLIDE_SECONDS,
      ease: 'easeOut',
      onUpdate: placeAt,
    })
    return () => glide.stop()
  }, [isMapReady, plan, selectedRoute, selectedPathDistances, forecastHour])

  if (!MAPBOX_TOKEN) {
    return (
      <p className="map-message">
        Add VITE_MAPBOX_TOKEN to frontend/.env.local to show the map.
      </p>
    )
  }
  const hasTimeline = (plan?.corridor_forecast.hours.length ?? 0) > 0
  return (
    <div className="map-stack">
      <div ref={containerRef} className="route-map" />
      {hasTimeline && (
        <TripTimeline
          plan={plan}
          selectedRouteId={selectedRouteId}
          onSelectRoute={onSelectRoute}
          hour={forecastHour}
          onHourChange={setForecastHour}
          layer={heatmapLayer}
          onLayerChange={setHeatmapLayer}
        />
      )}
    </div>
  )
}
