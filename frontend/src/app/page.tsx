"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  CalendarClock,
  CheckCircle2,
  Loader2,
  PauseCircle,
  Play,
  Plus,
  RefreshCw,
  SearchX,
  ShieldCheck,
  TimerReset,
} from "lucide-react";

import {
  api,
  ApiError,
  BUSINESS_TOOLS,
  type BusinessToolId,
  type OrderRun,
  type SupervisorConfig,
} from "@/lib/api";
import { formatDate, formatDateTime, formatDurationUntil } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

const STATUS_STYLE: Record<string, string> = {
  running: "border-amber-200 bg-amber-50 text-amber-800",
  paused: "border-sky-200 bg-sky-50 text-sky-800",
  terminating: "border-rose-200 bg-rose-50 text-rose-800",
  completed: "border-emerald-200 bg-emerald-50 text-emerald-800",
  terminated: "border-rose-200 bg-rose-50 text-rose-800",
  failed: "border-red-200 bg-red-50 text-red-800",
};

type ToastState = { message: string; tone: "success" | "error" };

function Toast({ toast, onDone }: { toast: ToastState; onDone: () => void }) {
  useEffect(() => {
    const timeout = setTimeout(onDone, 3200);
    return () => clearTimeout(timeout);
  }, [onDone]);

  return (
    <div
      className={`fixed bottom-5 right-5 z-50 flex max-w-sm items-center gap-2 rounded-lg px-4 py-3 text-sm font-medium text-white shadow-xl ${
        toast.tone === "error" ? "bg-rose-900" : "bg-slate-950"
      }`}
      role="status"
    >
      {toast.tone === "error" ? <SearchX className="size-4" /> : <CheckCircle2 className="size-4 text-emerald-300" />}
      <span>{toast.message}</span>
    </div>
  );
}

function statusBadge(status: string) {
  return (
    <Badge variant="outline" className={STATUS_STYLE[status] ?? "border-border bg-muted text-muted-foreground"}>
      {status}
    </Badge>
  );
}

function emptyMemory(run: OrderRun) {
  if (run.status === "failed") return "Workflow failed before memory was written.";
  if (run.status === "completed" || run.status === "terminated") return "No final memory was recorded.";
  return "Waiting for the first agent update.";
}

export default function Dashboard() {
  const [runs, setRuns] = useState<OrderRun[]>([]);
  const [supervisors, setSupervisors] = useState<SupervisorConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const [templateName, setTemplateName] = useState("");
  const [baseInstruction, setBaseInstruction] = useState("");
  const [defaultWakeUpBehavior, setDefaultWakeUpBehavior] = useState("Review every 24 hours unless payment, shipment, refund, or customer events arrive.");
  const [modelChoice, setModelChoice] = useState("");
  const [selectedTools, setSelectedTools] = useState<BusinessToolId[]>(BUSINESS_TOOLS.map((tool) => tool.id));

  const [newRunOrderId, setNewRunOrderId] = useState("");
  const [selectedSupervisor, setSelectedSupervisor] = useState("");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [submitting, setSubmitting] = useState<"template" | "run" | null>(null);

  const loadData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const [loadedRuns, loadedSupervisors] = await Promise.all([
        api.getRuns(),
        api.getSupervisors(),
      ]);
      setRuns(loadedRuns);
      setSupervisors(loadedSupervisors);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Unable to load dashboard data.";
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    const initialLoad = async () => {
      await loadData();
    };

    void initialLoad();
    const interval = setInterval(() => {
      void loadData();
    }, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  const stats = useMemo(() => {
    const active = runs.filter((run) => run.status === "running").length;
    const paused = runs.filter((run) => run.status === "paused").length;
    const completed = runs.filter((run) => run.status === "completed").length;
    return { active, paused, completed, templates: supervisors.length };
  }, [runs, supervisors]);

  const toggleTool = (toolId: BusinessToolId) => {
    setSelectedTools((current) =>
      current.includes(toolId)
        ? current.filter((id) => id !== toolId)
        : [...current, toolId],
    );
  };

  const handleCreateSupervisor = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (selectedTools.length === 0) {
      setToast({ tone: "error", message: "Select at least one action." });
      return;
    }

    setSubmitting("template");
    try {
      await api.createSupervisor({
        name: templateName.trim(),
        base_instruction: baseInstruction.trim(),
        available_tools: selectedTools,
        default_wake_up_behavior: defaultWakeUpBehavior.trim() || null,
        model_choice: modelChoice.trim() || null,
      });
      setCreateDialogOpen(false);
      setTemplateName("");
      setBaseInstruction("");
      setModelChoice("");
      setSelectedTools(BUSINESS_TOOLS.map((tool) => tool.id));
      setToast({ tone: "success", message: "Supervisor template created." });
      await loadData();
    } catch (err) {
      setToast({ tone: "error", message: err instanceof ApiError ? err.message : "Template could not be created." });
    } finally {
      setSubmitting(null);
    }
  };

  const handleStartRun = async () => {
    const orderId = newRunOrderId.trim();
    if (!orderId || !selectedSupervisor) return;

    setSubmitting("run");
    try {
      await api.startRun({ order_id: orderId, supervisor_config_id: selectedSupervisor });
      setNewRunOrderId("");
      setSelectedSupervisor("");
      setRunDialogOpen(false);
      setToast({ tone: "success", message: `Workflow started for ${orderId}.` });
      await loadData();
    } catch (err) {
      setToast({ tone: "error", message: err instanceof ApiError ? err.message : "Run could not be started." });
    } finally {
      setSubmitting(null);
    }
  };

  if (loading) {
    return (
      <div className="grid gap-4">
        <div className="h-24 animate-pulse rounded-lg border border-border bg-white" />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((item) => (
            <div key={item} className="h-44 animate-pulse rounded-lg border border-border bg-white" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {toast && <Toast toast={toast} onDone={() => setToast(null)} />}

      <section className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium text-primary">
            <ShieldCheck className="size-4" />
            <span>AI workflow operations</span>
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-normal text-foreground">Order runs</h1>
            <p className="mt-1 max-w-2xl text-sm leading-6 text-muted-foreground">
              Monitor long-running supervisors, inspect memory, and drive order events from one control surface.
            </p>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button
            variant="outline"
            className="gap-2"
            onClick={() => loadData(true)}
            disabled={refreshing}
          >
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>

          <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
            <DialogTrigger render={
              <Button variant="outline" className="gap-2">
                <Plus className="size-4" />
                Template
              </Button>
            } />
            <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
              <DialogHeader>
                <DialogTitle>Create Supervisor Template</DialogTitle>
              </DialogHeader>
              <form onSubmit={handleCreateSupervisor} className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-1.5">
                    <Label htmlFor="name">Name</Label>
                    <Input
                      id="name"
                      value={templateName}
                      minLength={2}
                      maxLength={120}
                      required
                      placeholder="Electronics standard"
                      onChange={(event) => setTemplateName(event.target.value)}
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="model">Model</Label>
                    <Input
                      id="model"
                      value={modelChoice}
                      maxLength={120}
                      placeholder="llama3.1:8b"
                      onChange={(event) => setModelChoice(event.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="base_instruction">Base instruction</Label>
                  <Textarea
                    id="base_instruction"
                    value={baseInstruction}
                    required
                    minLength={20}
                    rows={6}
                    placeholder="Supervise this order until delivery. Escalate payment failures, shipment delays, refund requests, and customer messages."
                    className="resize-none"
                    onChange={(event) => setBaseInstruction(event.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="wake_behavior">Wake-up behavior</Label>
                  <Textarea
                    id="wake_behavior"
                    value={defaultWakeUpBehavior}
                    rows={3}
                    maxLength={1000}
                    className="resize-none"
                    onChange={(event) => setDefaultWakeUpBehavior(event.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Available actions</Label>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {BUSINESS_TOOLS.map((tool) => {
                      const checked = selectedTools.includes(tool.id);
                      return (
                        <label
                          key={tool.id}
                          className={`flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
                            checked ? "border-primary/40 bg-accent text-accent-foreground" : "border-border bg-white text-muted-foreground"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            className="size-4 accent-primary"
                            onChange={() => toggleTool(tool.id)}
                          />
                          <span>{tool.label}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <Button type="submit" disabled={submitting === "template"} className="w-full gap-2">
                  {submitting === "template" && <Loader2 className="size-4 animate-spin" />}
                  Create template
                </Button>
              </form>
            </DialogContent>
          </Dialog>

          <Dialog open={runDialogOpen} onOpenChange={setRunDialogOpen}>
            <DialogTrigger render={
              <Button className="gap-2">
                <Play className="size-4" />
                Start Run
              </Button>
            } />
            <DialogContent className="sm:max-w-md">
              <DialogHeader>
                <DialogTitle>Start Order Supervisor</DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="space-y-1.5">
                  <Label htmlFor="order-id">Order ID</Label>
                  <Input
                    id="order-id"
                    value={newRunOrderId}
                    maxLength={80}
                    placeholder="ORD-12345"
                    onChange={(event) => setNewRunOrderId(event.target.value)}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label htmlFor="supervisor">Supervisor template</Label>
                  {supervisors.length === 0 ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                      Create a template before starting a run.
                    </div>
                  ) : (
                    <select
                      id="supervisor"
                      className="h-9 w-full rounded-lg border border-input bg-white px-2.5 text-sm outline-none transition focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                      value={selectedSupervisor}
                      onChange={(event) => setSelectedSupervisor(event.target.value)}
                    >
                      <option value="">Select template</option>
                      {supervisors.map((supervisor) => (
                        <option key={supervisor.id} value={supervisor.id}>
                          {supervisor.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
                <Button
                  onClick={handleStartRun}
                  disabled={!newRunOrderId.trim() || !selectedSupervisor || submitting === "run"}
                  className="w-full gap-2"
                >
                  {submitting === "run" && <Loader2 className="size-4 animate-spin" />}
                  Start workflow
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <SearchX className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "Running", value: stats.active, icon: TimerReset },
          { label: "Paused", value: stats.paused, icon: PauseCircle },
          { label: "Completed", value: stats.completed, icon: CheckCircle2 },
          { label: "Templates", value: stats.templates, icon: Boxes },
        ].map(({ label, value, icon: Icon }) => (
          <div key={label} className="rounded-lg border border-border bg-white px-4 py-3 shadow-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-sm font-medium text-muted-foreground">{label}</span>
              <Icon className="size-4 text-primary" />
            </div>
            <div className="mt-2 text-2xl font-semibold text-foreground">{value}</div>
          </div>
        ))}
      </section>

      {runs.length === 0 ? (
        <section className="flex min-h-80 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-white px-6 text-center">
          <div className="flex size-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Play className="size-5" />
          </div>
          <h2 className="mt-4 text-base font-semibold text-foreground">No order runs yet</h2>
          <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
            Create a template, then start an order workflow to see memory, actions, and lifecycle events.
          </p>
        </section>
      ) : (
        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {runs.map((run) => (
            <Link href={`/runs/${run.id}`} key={run.id} className="group block focus:outline-none">
              <Card className="h-full rounded-lg border-border bg-white shadow-sm transition group-hover:-translate-y-0.5 group-hover:border-primary/30 group-hover:shadow-md group-focus-visible:ring-3 group-focus-visible:ring-ring/40">
                <CardHeader className="border-b border-border/70 pb-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <CardTitle className="truncate text-base font-semibold text-foreground">
                        {run.order_id}
                      </CardTitle>
                      <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{run.id}</p>
                    </div>
                    {statusBadge(run.status)}
                  </div>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col gap-4 pt-4">
                  <p className="min-h-16 text-sm leading-6 text-muted-foreground line-clamp-3">
                    {run.memory_summary || run.final_summary || emptyMemory(run)}
                  </p>

                  <div className="grid grid-cols-2 gap-3 rounded-lg border border-border bg-muted/30 p-3 text-xs">
                    <div>
                      <div className="font-medium text-muted-foreground">Started</div>
                      <div className="mt-1 text-foreground">{formatDate(run.created_at)}</div>
                    </div>
                    <div>
                      <div className="font-medium text-muted-foreground">Wake-up</div>
                      <div className="mt-1 text-foreground">{formatDurationUntil(run.next_wake_at)}</div>
                    </div>
                  </div>

                  <div className="mt-auto flex items-center justify-between border-t border-border pt-3">
                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <CalendarClock className="size-3.5" />
                      {formatDateTime(run.updated_at)}
                    </span>
                    <span className="flex items-center gap-1 text-xs font-medium text-primary transition group-hover:gap-1.5">
                      Open <ArrowRight className="size-3.5" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </section>
      )}
    </div>
  );
}
