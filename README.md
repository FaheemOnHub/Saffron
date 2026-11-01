# Saffron

Pick the safest truck route between two places, based on forecast weather along the way, the load weight, and travel time.

You enter an origin, a destination, a departure time and a load weight. Saffron gets up to 3 truck routes, checks the forecast at checkpoints every 10, 25 or 50 miles (for the hour the truck will actually be there), rates each checkpoint with the risk rules, and recommends a route. The map shows every route, the checkpoints with their ETAs and risk, and a weather heatmap along the corridor with a 0–48 hour slider.

Built with Django for the API, React and Vite for the UI, Mapbox GL for the map, HERE for geocoding and truck routing, and Open-Meteo for forecasts.

## Run it locally

You need Python 3.13+, Node 20.19+, a HERE API key and a public Mapbox token.

```bash
# Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add HERE_API_KEY; keep DJANGO_DEBUG=true for local
python manage.py runserver    # http://127.0.0.1:8000

# Frontend (second terminal)
cd frontend
npm install
cp .env.example .env.local    # add VITE_MAPBOX_TOKEN
npm run dev                   # http://localhost:5173
```

## How it works

1. **Geocode and route.** HERE truck routing with the truck's gross weight, asking for 2 alternatives. If HERE returns fewer than 3 distinct routes, we force detours through points beside the trip's midpoint and keep any that are real alternatives (see below).
2. **Checkpoints.** Placed at the origin, every N miles, and the destination. ETAs come from HERE's per-stretch drive times, so slow city sections push later checkpoints back realistically.
3. **Weather.** Open-Meteo hourly forecast for the hour the truck reaches each checkpoint. Wind is in mph and precipitation in inches, straight from the API.
4. **Risk.** Each checkpoint gets the worst of its wind, rain and snow level, after the load rules.
5. **Ranking.** Strictly in this order:
   1. fewest Severe miles
   2. fewest High miles
   3. lowest average risk
   4. shortest travel time

   Routes with any No Travel miles always rank last. The recommended route says which rule decided it.
6. **Heatmap.** A grid of up to 150 points within 30 miles of the routes, with 49 hourly forecasts each. The slider only changes which hour the map reads, so it doesn't refetch.

## Assumptions and decisions

- **Boundary values go to the higher level.** The table's ranges touch (rain 0.25 is listed under both Moderate and High); 0.25 counts as High. The exception is No Travel for rain and snow, which the table writes as strictly greater (`>1.00`, `>3.0`), so exactly 1.00 in/hr rain is Severe.
- **Sustained wind decides the risk level.** The thresholds (25/35/45/55 mph) match sustained wind, not gusts. Gusts are shown separately, with a warning when they reach 35 mph while sustained wind is lower.
- **The load rules only raise the wind level.** 45–54 mph with more than 30,000 lb is No Travel; 35–44 mph with more than 40,000 lb is Severe.
- **Gross weight = load + 35,000 lb.** Routing needs the whole truck's weight; 35,000 lb is a typical empty tractor and 53 ft trailer.
- **Miles per level come from checkpoint coverage.** Each checkpoint stands for the road halfway to its neighbours, so the coverage adds up to the route length. Miles and the average are rounded (0.1 mi, 0.01) before comparing, so sampling noise can't outweigh an hour of travel time.
- **Miles with no forecast are counted separately** and left out of the average, not treated as Low.
- **Departure must be within the next 7 days**, so forecasts are meaningful and long trips stay inside Open-Meteo's ~16-day range.
- **Heatmap hour 0 is the departure hour.** The Wind/Rain/Snow layers are drawn on the same 0–4 scale as risk, using each condition's own thresholds. They are for display only and never affect the ranking.
- **Times are shown in the viewer's timezone**, with the zone name.

## Project layout

```
backend/planner/
  risk.py          risk table, load rules, heatmap scores
  routing.py       HERE geocoding and truck routes, forced detours
  checkpoints.py   checkpoint placement and ETAs
  weather.py       Open-Meteo forecasts (batched, parallel)
  assessment.py    per-route risk summary and ranking
  corridor.py      heatmap grid and hourly frames
  trip_planner.py  runs the pipeline
  views.py         GET /api/trip-plan, GET /api/health
frontend/src/
  components/      TripForm, RouteList, RiskStrip, RouteMap, HeatmapControls
  mapData.js       plan -> Mapbox sources and expressions
```
