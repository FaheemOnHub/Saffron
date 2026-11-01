import { formatDuration, formatMiles } from './format'

export function routeName(route) {
  return route.highways?.length ? route.highways.join(' / ') : `Route ${route.rank}`
}

export function ordinal(rank) {
  return { 1: '1st', 2: '2nd', 3: '3rd' }[rank] ?? `${rank}th`
}

// How each ranking rule's value reads for one route. Keys match the API's ranking_rules.
const RULE_VALUES = {
  no_travel_miles: (route) => formatMiles(route.risk_summary.miles_by_level.no_travel),
  severe_miles: (route) => formatMiles(route.risk_summary.miles_by_level.severe),
  high_miles: (route) => formatMiles(route.risk_summary.miles_by_level.high),
  average_risk: (route) => route.risk_summary.average_risk.toFixed(2),
  travel_time: (route) => formatDuration(route.duration_s),
}

// One row per ranking rule, in priority order, each naming the rank pairs it decides.
// `routes` must already be sorted best first, as the API sends them.
export function rankingRows(plan) {
  return plan.ranking_rules.map((rule) => ({
    key: rule.key,
    label: rule.label.charAt(0).toUpperCase() + rule.label.slice(1),
    values: plan.routes.map((route) => RULE_VALUES[rule.key](route)),
    decides: plan.routes
      .slice(0, -1)
      .filter((route) => route.beats_next_on === rule.key)
      .map((route) => `Decides ${ordinal(route.rank)} vs ${ordinal(route.rank + 1)}`),
  }))
}
