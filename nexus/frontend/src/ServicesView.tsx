import { fetchServices, type Service } from "./api";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 30_000;

const STATUS_LABELS: Record<Service["status"], string> = {
  up: "Up",
  down: "Down",
  unknown: "No live check",
};

function ServiceCard({ service }: { service: Service }) {
  return (
    <article className="service-card">
      <div className="service-header">
        <span className="service-name">{service.name}</span>
        <span className={`service-status ${service.status}`}>
          <span className={`status-dot ${service.status === "up" ? "up" : "down"}`} />
          {STATUS_LABELS[service.status]}
        </span>
      </div>
      <p className="service-description">{service.description}</p>

      {service.facts.length > 0 && (
        <dl className="service-facts">
          {service.facts.map((fact) => (
            <div key={fact.label} className="service-fact">
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}

      {service.decision && (
        <div className="service-decision">
          <span className="service-decision-label">Chosen over</span>{" "}
          <strong>{service.decision.alternative}</strong>. {service.decision.reason}{" "}
          <a href={service.decision.adr.url} target="_blank" rel="noreferrer">
            {service.decision.adr.label}
          </a>
        </div>
      )}

      {service.links.length > 0 && (
        <div className="service-links">
          {service.links.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="detail-link"
            >
              {link.label} &rarr;
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

export function ServicesView() {
  const { data: services, error } = usePolling(fetchServices, POLL_INTERVAL_MS);

  if (error && !services) {
    return <div className="graph-error">Can't reach the Nexus backend: {error}</div>;
  }
  if (!services) {
    return <div className="graph-loading">Loading services…</div>;
  }

  // Grouped by layer in the order the backend lists them, which runs from the hardware up.
  const layers = [...new Set(services.map((s) => s.layer))];

  return (
    <div className="view-scroll">
      {layers.map((layer) => (
        <section key={layer} className="service-layer">
          <h2 className="service-layer-title">{layer}</h2>
          <div className="service-grid">
            {services
              .filter((s) => s.layer === layer)
              .map((s) => (
                <ServiceCard key={s.id} service={s} />
              ))}
          </div>
        </section>
      ))}
    </div>
  );
}
