export function MapLegend({rows=[]}:{rows?:string[]}){return <div className="map-legend" data-testid="map-legend">{rows.map(row=><div key={row}>{row}</div>)}</div>}
