import { X } from 'lucide-react'
import { useEffect, useRef } from 'react'
import { ordinal, rankingRows, routeName } from '../compare'
import { formatMiles, formatTime } from '../format'
import RiskStrip from './RiskStrip'

// Native <dialog> + showModal() gives focus trapping, Escape to close and a
// backdrop without a UI library.
export default function CompareDialog({ plan, isOpen, onClose, levelLabels }) {
  const dialogRef = useRef(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (isOpen && !dialog.open) dialog.showModal()
    if (!isOpen && dialog.open) dialog.close()
  }, [isOpen])

  const rows = rankingRows(plan)
  const columnClass = (route) => (route.is_recommended ? 'is-recommended' : undefined)

  return (
    <dialog ref={dialogRef} className="compare-dialog" onClose={onClose} aria-labelledby="compare-heading">
      <div className="compare-header">
        <div>
          <h2 id="compare-heading">Compare routes</h2>
          <p>Rows follow the ranking rules, top to bottom. A tag marks the rule that decided each place.</p>
        </div>
        <button type="button" className="close-button" onClick={onClose} aria-label="Close comparison">
          <X className="size-5" aria-hidden="true" />
        </button>
      </div>

      <div className="compare-scroll">
        <table className="compare-table">
          <thead>
            <tr>
              <th scope="col">Ranking rule</th>
              {plan.routes.map((route) => (
                <th scope="col" key={route.id} className={columnClass(route)}>
                  <span className="compare-rank">{route.is_recommended ? '1st, recommended' : ordinal(route.rank)}</span>
                  <span className="compare-route">{routeName(route)}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.key} className={row.decides.length > 0 ? 'is-deciding' : undefined}>
                <th scope="row">
                  {row.label}
                  {row.decides.map((tag) => <span key={tag} className="decides-tag">{tag}</span>)}
                </th>
                {row.values.map((value, index) => (
                  <td key={plan.routes[index].id} className={columnClass(plan.routes[index])}>{value}</td>
                ))}
              </tr>
            ))}
            <tr className="is-detail">
              <th scope="row">Risk along the route</th>
              {plan.routes.map((route) => (
                <td key={route.id} className={columnClass(route)}>
                  <RiskStrip checkpoints={route.checkpoints} levelLabels={levelLabels} />
                </td>
              ))}
            </tr>
            <tr className="is-detail">
              <th scope="row">Distance</th>
              {plan.routes.map((route) => (
                <td key={route.id} className={columnClass(route)}>{formatMiles(route.distance_miles)}</td>
              ))}
            </tr>
            <tr className="is-detail">
              <th scope="row">Arrives</th>
              {plan.routes.map((route) => (
                <td key={route.id} className={columnClass(route)}>{formatTime(route.arrival_time)}</td>
              ))}
            </tr>
            <tr className="is-detail">
              <th scope="row">Strong gusts</th>
              {plan.routes.map((route) => {
                const count = route.risk_summary.gust_warning_count
                return (
                  <td key={route.id} className={columnClass(route)}>
                    {count === 0 ? 'None' : `${count} checkpoint${count > 1 ? 's' : ''}`}
                  </td>
                )
              })}
            </tr>
          </tbody>
        </table>
      </div>
    </dialog>
  )
}
