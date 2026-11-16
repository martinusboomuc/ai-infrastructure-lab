import type { Service } from "./api";

const STATUS_LABELS: Record<Service["status"], string> = {
  up: "Up",
  down: "Down",
  unknown: "No live check",
};

// Detail for the tool whose plinth was clicked: what it does here, what it was chosen over and
// why, and the links out to it. The same content as a card in the list view.
export function ServiceDetailPanel({
  service,
  onClose,
}: {
  service: Service;
  onClose: () => void;
}) {
  return (
    <aside className="detail-panel">
      <div className="detail-header">
        <div>
          <div className="detail-label">{service.name}</div>
          <div className="detail-type">{service.layer}</div>
        </div>
        <button className="detail-close" onClick={onClose} aria-label="Close detail panel">
          &times;
        </button>
      </div>

      <div className={`service-status detail-service-status ${service.status}`}>
        <span className={`status-dot ${service.status === "up" ? "up" : "down"}`} />
        {STATUS_LABELS[service.status]}
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

      <div className="detail-links">
        <div className="detail-links-heading">Open</div>
        {service.links.length > 0 ? (
          service.links.map((link) => (
            <a
              key={link.url}
              href={link.url}
              target="_blank"
              rel="noreferrer"
              className="detail-link"
            >
              {link.label} &rarr;
            </a>
          ))
        ) : (
          <div className="detail-links-empty">No links recorded for this tool.</div>
        )}
      </div>
    </aside>
  );
}
