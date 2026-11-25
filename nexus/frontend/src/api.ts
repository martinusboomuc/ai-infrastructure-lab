export interface HostHealth {
  cpu_pct: number | null;
  memory_pct: number | null;
  disk_pct: number | null;
  up: boolean | null;
}

export interface QuickLink {
  label: string;
  url: string;
}

export interface TopologyNode {
  id: string;
  label: string;
  type: "host" | "vm" | "laptop" | "phone";
  parent: string | null;
  online: boolean;
  tailscale_ip: string | null;
  health: HostHealth | null;
  links: QuickLink[];
}

// Always relative: in production nginx reverse-proxies /api/ to the backend container by its
// Compose service name (see nginx.conf); in dev, Vite's own server.proxy does the equivalent
// (see vite.config.ts). The frontend's own code never needs to know the backend's real address.
export async function fetchTopology(): Promise<TopologyNode[]> {
  const response = await fetch("/api/topology");
  if (!response.ok) {
    throw new Error(`topology fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.nodes;
}

export interface Decision {
  alternative: string;
  reason: string;
  adr: QuickLink;
}

// A live value the backend reads for a service, such as the BankML model's ROC-AUC.
export interface Fact {
  label: string;
  value: string;
}

export interface Service {
  id: string;
  name: string;
  layer: string;
  description: string;
  links: QuickLink[];
  decision: Decision | null;
  status: "up" | "down" | "unknown";
  facts: Fact[];
}

export async function fetchServices(): Promise<Service[]> {
  const response = await fetch("/api/services");
  if (!response.ok) {
    throw new Error(`services fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.services;
}

export interface Alert {
  name: string;
  folder: string;
  severity: string;
  target: string;
  summary: string;
  starts_at: string;
  silenced: boolean;
}

export interface AlertsResponse {
  configured: boolean;
  alerts: Alert[];
  channels: QuickLink[];
  grafana_url: string;
  error: string | null;
}

export async function fetchAlerts(): Promise<AlertsResponse> {
  const response = await fetch("/api/alerts");
  if (!response.ok) {
    throw new Error(`alerts fetch failed: ${response.status}`);
  }
  return response.json();
}

// BankML's registered models, read live from the MLflow registry and the monitoring gauges.
export interface ModelVersion {
  version: string;
  aliases: string[];
  created_ms: number;
  model_type: string;
  gate: string;
  gate_reasons: string[];
  promotion: string;
  metrics: Partial<Record<"pr_auc" | "roc_auc" | "recall_at_target_fpr" | "expected_cost", number>>;
  description: string;
  mlflow_url: string;
}

export interface Monitoring {
  performance: Partial<
    Record<
      "measured" | "n_labeled" | "n_positive" | "roc_auc" | "test_roc_auc" | "roc_auc_drop",
      number
    >
  >;
  drift_detected: boolean | null;
  drift_last_run_s: number | null;
}

export interface BankmlModel {
  domain: string;
  title: string;
  purpose: string;
  registered_name: string;
  production_version: string | null;
  versions: ModelVersion[];
  monitoring: Monitoring;
  error: string | null;
}

export async function fetchBankmlModels(): Promise<BankmlModel[]> {
  const response = await fetch("/api/bankml/models");
  if (!response.ok) {
    throw new Error(`models fetch failed: ${response.status}`);
  }
  const data = await response.json();
  return data.models;
}
