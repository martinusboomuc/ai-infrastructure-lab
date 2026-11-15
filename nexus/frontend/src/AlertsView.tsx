import { fetchAlerts, type Alert, type AlertsResponse } from "./api";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 30_000;

function since(iso: string): string {
  const minutes = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.floor(hours / 24)} days ago`;
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <article className={`alert-row ${alert.silenced ? "silenced" : ""}`}>
      <div className="alert-header">
        <span className="alert-name">{alert.name}</span>
        {alert.severity && <span className="alert-severity">{alert.severity}</span>}
        {alert.silenced && <span className="alert-severity">silenced</span>}
        <span className="alert-since">{since(alert.starts_at)}</span>
      </div>
      <div className="alert-meta">
        {alert.folder}
        {alert.target && ` · ${alert.target}`}
      </div>
      {alert.summary && <p className="alert-summary">{alert.summary}</p>}
    </article>
  );
}

// The alert list itself, without the polling: the 3D room's alerts drawer and the list view
// both render it, from data the caller already holds.
export function AlertsList({ data }: { data: AlertsResponse }) {
  return (
    <>
      <section className="alerts-links">
        <a href={data.grafana_url} target="_blank" rel="noreferrer" className="detail-link">
          Alert rules in Grafana &rarr;
        </a>
        {data.channels.map((channel) => (
          <a
            key={channel.url}
            href={channel.url}
            target="_blank"
            rel="noreferrer"
            className="detail-link"
          >
            Discord {channel.label} &rarr;
          </a>
        ))}
      </section>

      {!data.configured && (
        <p className="alerts-empty">
          Alerts are not configured: the backend has no Grafana token. See the Nexus README.
        </p>
      )}
      {data.error && <p className="graph-error">Grafana did not answer ({data.error}).</p>}
      {data.configured && !data.error && data.alerts.length === 0 && (
        <p className="alerts-empty">No alerts firing.</p>
      )}
      {data.alerts.map((alert) => (
        <AlertRow key={`${alert.name}-${alert.target}-${alert.starts_at}`} alert={alert} />
      ))}
    </>
  );
}

export function AlertsView() {
  const { data, error } = usePolling(fetchAlerts, POLL_INTERVAL_MS);

  if (error && !data) {
    return <div className="graph-error">Can't reach the Nexus backend: {error}</div>;
  }
  if (!data) {
    return <div className="graph-loading">Loading alerts…</div>;
  }

  return (
    <div className="view-scroll">
      <AlertsList data={data} />
    </div>
  );
}
