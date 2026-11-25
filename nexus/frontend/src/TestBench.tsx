import { useEffect, useMemo, useState } from "react";
import { fetchExamples, predict, type ExamplesResponse, type Prediction } from "./api";

// Which object in a request holds the fields a person edits, and what each outcome means.
const DOMAINS: Record<
  string,
  { title: string; editable: string; positive: string; negative: string; noun: string }
> = {
  credit: {
    title: "Credit Risk",
    editable: "applicant",
    positive: "defaulted",
    negative: "repaid",
    noun: "applicant",
  },
  fraud: {
    title: "Fraud Detection",
    editable: "transaction",
    positive: "fraud",
    negative: "legitimate",
    noun: "transaction",
  },
};

type Fields = Record<string, unknown>;

function historyRows(request: Record<string, unknown>, editable: string): number {
  return Object.entries(request)
    .filter(([key, value]) => key !== editable && Array.isArray(value))
    .reduce((total, [, value]) => total + (value as unknown[]).length, 0);
}

// Values come back from the inputs as text; each is turned back into the type the example had,
// so the API sees the same request shape. An emptied number becomes null, which the API accepts
// only where the field is optional.
function parseFields(original: Fields, edited: Record<string, string>): Fields {
  const result: Fields = {};
  for (const [key, value] of Object.entries(original)) {
    const text = edited[key];
    if (text === undefined) {
      result[key] = value;
    } else if (typeof value === "number" || value === null) {
      result[key] = text.trim() === "" ? null : Number(text);
    } else {
      result[key] = text;
    }
  }
  return result;
}

function Result({
  prediction,
  outcome,
}: {
  prediction: Prediction;
  // What actually happened to this case, or why it is unknown.
  outcome: string;
}) {
  const flagged = prediction.decision === "flag";
  return (
    <div className="bench-result">
      <div className={`bench-decision ${flagged ? "flag" : "pass"}`}>
        {flagged ? "Flagged for review" : "Passed"}
      </div>
      <dl className="service-facts">
        <div className="service-fact">
          <dt>Score</dt>
          <dd>{prediction.score.toPrecision(4)}</dd>
        </div>
        <div className="service-fact">
          <dt>Threshold</dt>
          <dd>{prediction.threshold.toPrecision(4)}</dd>
        </div>
        <div className="service-fact">
          <dt>Model</dt>
          <dd>v{prediction.model_version}</dd>
        </div>
        <div className="service-fact">
          <dt>Actual outcome</dt>
          <dd>{outcome}</dd>
        </div>
      </dl>
      {prediction.reason_codes.length > 0 && (
        <table className="model-versions">
          <thead>
            <tr>
              <th>Reason</th>
              <th className="num">Contribution</th>
            </tr>
          </thead>
          <tbody>
            {prediction.reason_codes.map((r) => (
              <tr key={r.feature}>
                <td>{r.feature}</td>
                <td className="num">
                  {r.shap_value > 0 ? "+" : ""}
                  {r.shap_value.toFixed(3)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="bench-note">
        Contributions are SHAP values in log-odds: positive pushes towards a flag. Logged as test
        traffic, which drift and performance monitoring skip.
      </p>
    </div>
  );
}

export function TestBench() {
  const [domain, setDomain] = useState("credit");
  return (
    <article className="service-card bench">
      <div className="service-header">
        <span className="service-name">Test bench</span>
        <span className="bench-domains">
          {Object.entries(DOMAINS).map(([key, d]) => (
            <button
              key={key}
              className={`app-tab ${key === domain ? "active" : ""}`}
              onClick={() => setDomain(key)}
            >
              {d.title}
            </button>
          ))}
        </span>
      </div>
      {/* Keyed by domain, so switching starts from a clean state. */}
      <DomainBench key={domain} domain={domain} />
    </article>
  );
}

function DomainBench({ domain }: { domain: string }) {
  const [examples, setExamples] = useState<ExamplesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState(0);
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [sending, setSending] = useState(false);

  const config = DOMAINS[domain];

  useEffect(() => {
    let cancelled = false;
    fetchExamples(domain)
      .then((data) => !cancelled && setExamples(data))
      .catch((e: Error) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [domain]);

  const example = examples?.examples[selected];
  const fields = useMemo(
    () => (example ? (example.request[config.editable] as Fields) : {}),
    [example, config.editable],
  );
  const edited = Object.entries(edits).some(([key, text]) => String(fields[key] ?? "") !== text);

  async function send() {
    if (!example) return;
    setSending(true);
    setError(null);
    setPrediction(null);
    try {
      const request = { ...example.request, [config.editable]: parseFields(fields, edits) };
      setPrediction(await predict(domain, request));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  return (
    <>
      <p className="service-description">
        Real {config.noun}s from the held-out test split, which the model never trained on. Pick
        one, change any field, and send it to the model in production.
      </p>

      {error && <div className="graph-error">{error}</div>}
      {!examples && !error && <div className="graph-loading">Loading examples…</div>}

      {examples && example && (
        <>
          <label className="bench-picker">
            <span>Example</span>
            <select
              value={selected}
              onChange={(e) => {
                setSelected(Number(e.target.value));
                setEdits({});
                setPrediction(null);
              }}
            >
              {examples.examples.map((ex, i) => (
                <option key={ex.id} value={i}>
                  {ex.id} ({ex.outcome === 1 ? config.positive : config.negative})
                </option>
              ))}
            </select>
          </label>

          <div className="bench-fields">
            {Object.entries(fields).map(([key, value]) => (
              <label key={key} className="bench-field">
                <span>{key}</span>
                <input
                  value={edits[key] ?? (value === null ? "" : String(value))}
                  inputMode={typeof value === "number" ? "decimal" : "text"}
                  onChange={(e) => setEdits({ ...edits, [key]: e.target.value })}
                />
              </label>
            ))}
          </div>
          <p className="bench-note">
            Sent with {historyRows(example.request, config.editable)} rows of history as recorded,
            not editable here.
          </p>

          <div className="service-links">
            <button className="bench-send" onClick={send} disabled={sending}>
              {sending ? "Scoring… (a cold start can take a minute)" : "Score with production model"}
            </button>
            {edited && (
              <button className="app-tab" onClick={() => setEdits({})}>
                Reset fields
              </button>
            )}
          </div>

          {prediction && (
            <Result
              prediction={prediction}
              outcome={
                edited
                  ? "unknown: the case was edited"
                  : example.outcome === 1
                    ? config.positive
                    : config.negative
              }
            />
          )}
        </>
      )}
    </>
  );
}
