import { fetchBankmlModels, type BankmlModel, type ModelVersion } from "./api";
import { usePolling } from "./usePolling";

const POLL_INTERVAL_MS = 60_000;
// mlops ADR-0021: a version is measured in production once this many predictions have outcomes.
const MIN_LABELED = 500;

function fmt(value: number | undefined, digits = 3): string {
  return value === undefined ? "–" : value.toFixed(digits);
}

function pct(value: number | undefined): string {
  return value === undefined ? "–" : `${(value * 100).toFixed(1)}%`;
}

function date(ms: number): string {
  return ms ? new Date(ms).toISOString().slice(0, 10) : "–";
}

function GateNote({ version }: { version: ModelVersion }) {
  if (version.gate === "failed") {
    return (
      <div className="model-gate failed">
        <strong>Failed the gate:</strong> {version.gate_reasons.join("; ")}.{" "}
        <span className="model-gate-promotion">{version.promotion}</span>
      </div>
    );
  }
  if (version.gate === "passed") {
    return (
      <div className="model-gate passed">
        <strong>Passed the gate.</strong> {version.promotion}
      </div>
    );
  }
  return (
    <div className="model-gate">
      <strong>Gate not evaluated.</strong> {version.promotion}
    </div>
  );
}

function ProductionPanel({ model, version }: { model: BankmlModel; version: ModelVersion }) {
  const perf = model.monitoring.performance;
  let live: string;
  if (perf.measured === 1) {
    live = `${fmt(perf.roc_auc)} (drop ${fmt(perf.roc_auc_drop)} against test)`;
  } else if (perf.n_labeled !== undefined) {
    live = `waiting for outcomes, ${perf.n_labeled} of ${MIN_LABELED}`;
  } else {
    live = "not measured yet";
  }
  let drift: string;
  if (model.monitoring.drift_detected === null) {
    drift = "not checked yet";
  } else {
    drift = model.monitoring.drift_detected ? "drift detected" : "no drift";
  }

  return (
    <div className="model-production">
      <dl className="service-facts">
        <div className="service-fact">
          <dt>Serving</dt>
          <dd>
            v{version.version}, {version.model_type}, registered {date(version.created_ms)}
          </dd>
        </div>
        <div className="service-fact">
          <dt>Test PR-AUC</dt>
          <dd>{fmt(version.metrics.pr_auc)}</dd>
        </div>
        <div className="service-fact">
          <dt>Test ROC-AUC</dt>
          <dd>{fmt(version.metrics.roc_auc)}</dd>
        </div>
        <div className="service-fact">
          <dt>Recall at target</dt>
          <dd>{pct(version.metrics.recall_at_target_fpr)}</dd>
        </div>
        <div className="service-fact">
          <dt>Live ROC-AUC</dt>
          <dd>{live}</dd>
        </div>
        <div className="service-fact">
          <dt>Inputs</dt>
          <dd>{drift}</dd>
        </div>
      </dl>
      <GateNote version={version} />
    </div>
  );
}

function VersionTable({ versions }: { versions: ModelVersion[] }) {
  return (
    <table className="model-versions">
      <thead>
        <tr>
          <th>Version</th>
          <th>Role</th>
          <th>Type</th>
          <th>Gate</th>
          <th className="num">PR-AUC</th>
          <th className="num">ROC-AUC</th>
          <th className="num">Recall</th>
          <th>Registered</th>
        </tr>
      </thead>
      <tbody>
        {versions.map((v) => (
          <tr key={v.version}>
            <td>
              <a href={v.mlflow_url} target="_blank" rel="noreferrer">
                v{v.version}
              </a>
            </td>
            <td>{v.aliases.length ? v.aliases.join(", ") : "–"}</td>
            <td>{v.model_type || "–"}</td>
            <td>{v.gate || "–"}</td>
            <td className="num">{fmt(v.metrics.pr_auc)}</td>
            <td className="num">{fmt(v.metrics.roc_auc)}</td>
            <td className="num">{pct(v.metrics.recall_at_target_fpr)}</td>
            <td>{date(v.created_ms)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function ModelCard({ model }: { model: BankmlModel }) {
  const production = model.versions.find((v) => v.version === model.production_version);
  return (
    <article className="service-card model-card">
      <div className="service-header">
        <span className="service-name">{model.title}</span>
        <span className={`service-status ${production ? "up" : "down"}`}>
          <span className={`status-dot ${production ? "up" : "down"}`} />
          {production ? `v${production.version} in production` : "Nothing in production"}
        </span>
      </div>
      <p className="service-description">{model.purpose}</p>
      {model.error && <div className="graph-error">Can't read the registry: {model.error}</div>}
      {production && <ProductionPanel model={model} version={production} />}
      {model.versions.length > 0 && <VersionTable versions={model.versions} />}
    </article>
  );
}

export function BankmlView() {
  const { data: models, error } = usePolling(fetchBankmlModels, POLL_INTERVAL_MS);

  if (error && !models) {
    return <div className="graph-error">Can't reach the Nexus backend: {error}</div>;
  }
  if (!models) {
    return <div className="graph-loading">Loading models…</div>;
  }

  return (
    <div className="view-scroll">
      <section className="service-layer">
        <h2 className="service-layer-title">Models</h2>
        <div className="model-grid">
          {models.map((m) => (
            <ModelCard key={m.domain} model={m} />
          ))}
        </div>
      </section>
    </div>
  );
}
