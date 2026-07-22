const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";
const TENANT_ID = process.env.NEXT_PUBLIC_TENANT_ID || "demo";

export const BUSINESS_TOOLS = [
  { id: "message_fulfillment_team", label: "Fulfillment" },
  { id: "message_payments_team", label: "Payments" },
  { id: "message_logistics_team", label: "Logistics" },
  { id: "message_customer", label: "Customer" },
  { id: "create_internal_note", label: "Internal note" },
] as const;

export const ORDER_EVENTS = [
  { type: "order_created", label: "Order created" },
  { type: "payment_confirmed", label: "Payment confirmed" },
  { type: "payment_failed", label: "Payment failed" },
  { type: "shipment_created", label: "Shipment created" },
  { type: "shipment_delayed", label: "Shipment delayed" },
  { type: "customer_message_received", label: "Customer message" },
  { type: "refund_requested", label: "Refund requested" },
  { type: "no_update_for_n_hours", label: "No update" },
  { type: "delivered", label: "Delivered" },
] as const;

export type BusinessToolId = (typeof BUSINESS_TOOLS)[number]["id"];
export type RunStatus = "running" | "paused" | "terminating" | "completed" | "terminated" | "failed";
export type SleepState = "awake" | "sleeping" | "paused" | "completed" | "terminated" | "failed";

export interface SupervisorConfig {
  id: string;
  name: string;
  base_instruction: string;
  available_tools: BusinessToolId[];
  default_wake_up_behavior?: string | null;
  model_choice?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OrderRun {
  id: string;
  order_id: string;
  supervisor_config_id: string;
  status: RunStatus;
  sleep_state: SleepState;
  next_wake_at?: string | null;
  memory_summary?: string | null;
  final_summary?: string | null;
  final_learnings?: string | null;
  final_recommendations?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActivityLog {
  id: number;
  run_id: string;
  activity_type: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface CreateSupervisorInput {
  name: string;
  base_instruction: string;
  available_tools: BusinessToolId[];
  default_wake_up_behavior?: string | null;
  model_choice?: string | null;
}

export interface StartRunInput {
  order_id: string;
  supervisor_config_id: string;
}

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(message: string, status: number, details: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

function errorMessage(payload: unknown, fallback: string) {
  if (payload && typeof payload === "object") {
    const record = payload as Record<string, unknown>;
    if (typeof record.detail === "string") return record.detail;
    if (typeof record.user_message === "string") return record.user_message;
    if (Array.isArray(record.detail)) return "Please check the highlighted fields and try again.";
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Tenant-ID", TENANT_ID);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    cache: init.cache ?? "no-store",
  });

  const text = await response.text();
  let payload: unknown = null;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text };
    }
  }

  if (!response.ok) {
    throw new ApiError(
      errorMessage(payload, `Request failed with status ${response.status}`),
      response.status,
      payload,
    );
  }

  return payload as T;
}

export const api = {
  getSupervisors: () => request<SupervisorConfig[]>("/supervisors"),

  createSupervisor: (data: CreateSupervisorInput) =>
    request<SupervisorConfig>("/supervisors", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  getRuns: () => request<OrderRun[]>("/runs"),

  getRun: (id: string) => request<OrderRun>(`/runs/${id}`),

  getRunActivities: (id: string) => request<ActivityLog[]>(`/runs/${id}/activities`),

  startRun: (data: StartRunInput) =>
    request<OrderRun>("/runs", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  sendEvent: (id: string, eventType: string, details: Record<string, unknown> = {}) =>
    request<{ status: string }>(`/runs/${id}/events`, {
      method: "POST",
      body: JSON.stringify({ event_type: eventType, details }),
    }),

  sendInstruction: (id: string, instruction: string) =>
    request<{ status: string }>(`/runs/${id}/instructions`, {
      method: "POST",
      body: JSON.stringify({ instruction }),
    }),

  pauseRun: (id: string) => request<{ status: string }>(`/runs/${id}/interrupt`, { method: "POST" }),

  resumeRun: (id: string) => request<{ status: string }>(`/runs/${id}/resume`, { method: "POST" }),

  terminateRun: (id: string) => request<{ status: string }>(`/runs/${id}/terminate`, { method: "POST" }),
};
