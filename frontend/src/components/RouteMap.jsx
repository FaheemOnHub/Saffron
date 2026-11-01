import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useEffect, useRef, useState } from 'react'
import {
  boundsOfRoutes,
  checkpointPopupHtml,
  checkpointsGeoJson,
  riskGradientExpression,
  routeLinesGeoJson,
} from '../mapData'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN
const CONTINENTAL_US = { center: [-98.5, 39.5], zoom: 3.4 }
const EMPTY_COLLECTION = { type: 'FeatureCollection', features: [] }
const SLATE = '#7C8B96'

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
  const [isMapReady, setIsMapReady] = useState(false)
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

    map.on('load', () => {
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
    map.fitBounds(boundsOfRoutes(plan.routes), { padding: 56, duration: 600 })
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

  if (!MAPBOX_TOKEN) {
    return (
      <p className="map-message">
        Add VITE_MAPBOX_TOKEN to frontend/.env.local to show the map.
      </p>
    )
  }
  return <div ref={containerRef} className="route-map" />
}
