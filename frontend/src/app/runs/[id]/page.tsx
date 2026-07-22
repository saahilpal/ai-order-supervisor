"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bell,
  Brain,
  CheckCircle2,
  ChevronRight,
  CirclePause,
  CirclePlay,
  ClipboardList,
  Clock,
  Loader2,
  MessageSquare,
  Moon,
  RefreshCw,
  Send,
  ShieldAlert,
  Square,
  TerminalSquare,
  TimerReset,
  Zap,
} from "lucide-react";

import { api, ApiError, ORDER_EVENTS, type ActivityLog, type OrderRun } from "@/lib/api";
import { compactJson, formatDateTime, formatDurationUntil, titleize } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
      {toast.tone === "error" ? <AlertTriangle className="size-4" /> : <CheckCircle2 className="size-4 text-emerald-300" />}
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

function detailString(details: Record<string, unknown>, key: string) {
  const value = details[key];
  return typeof value === "string" ? value : undefined;
}

function nestedDetailString(details: Record<string, unknown>, parent: string, key: string) {
  const value = details[parent];
  if (!value || typeof value !== "object") return undefined;
  const nested = value as Record<string, unknown>;
  return typeof nested[key] === "string" ? nested[key] : undefined;
}

function activityMeta(activity: ActivityLog) {
  const eventType = detailString(activity.details, "event_type");
  const toolName = detailString(activity.details, "tool_name");

  switch (activity.activity_type) {
    case "event":
      return { icon: Zap, tone: "text-sky-600 bg-sky-50 border-sky-200", title: eventType ? titleize(eventType) : "Event received" };
    case "agent_wakeup":
      return { icon: ShieldAlert, tone: "text-amber-700 bg-amber-50 border-amber-200", title: "Agent wake-up" };
    case "agent_action":
      return { icon: CheckCircle2, tone: "text-emerald-700 bg-emerald-50 border-emerald-200", title: toolName ? titleize(toolName) : "Tool executed" };
    case "agent_sleep_decision":
      return { icon: Moon, tone: "text-slate-700 bg-slate-50 border-slate-200", title: "Sleep decision" };
    case "manual_instruction":
      return { icon: MessageSquare, tone: "text-violet-700 bg-violet-50 border-violet-200", title: "Manual instruction" };
    case "run_paused":
      return { icon: CirclePause, tone: "text-sky-700 bg-sky-50 border-sky-200", title: "Run paused" };
    case "run_resumed":
      return { icon: CirclePlay, tone: "text-teal-700 bg-teal-50 border-teal-200", title: "Run resumed" };
    case "run_terminated":
      return { icon: Square, tone: "text-rose-700 bg-rose-50 border-rose-200", title: "Termination requested" };
    case "final_output":
      return { icon: ClipboardList, tone: "text-emerald-700 bg-emerald-50 border-emerald-200", title: "Final output" };
    case "agent_error":
    case "workflow_error":
      return { icon: AlertTriangle, tone: "text-red-700 bg-red-50 border-red-200", title: "Recoverable error" };
    default:
      return { icon: Clock, tone: "text-muted-foreground bg-muted border-border", title: titleize(activity.activity_type) };
  }
}

function activitySummary(activity: ActivityLog) {
  const { details } = activity;
  const instruction = detailString(details, "instruction");
  const message = detailString(details, "message") || nestedDetailString(details, "arguments", "message");
  const note = detailString(details, "note") || nestedDetailString(details, "arguments", "note");
  const finalSummary = detailString(details, "final_summary");
  const userMessage = detailString(details, "user_message");

  if (instruction) return instruction;
  if (message) return message;
  if (note) return note;
  if (finalSummary) return finalSummary;
  if (userMessage) return userMessage;

  const actionsCount = details.actions_count;
  const sleepDuration = details.sleep_duration_seconds;
  if (typeof actionsCount === "number") {
    return `${actionsCount} action${actionsCount === 1 ? "" : "s"} planned; next sleep ${sleepDuration ?? "default"} seconds.`;
  }

  return compactJson(details);
}

export default function RunDetails() {
  const params = useParams<{ id: string }>();
  const runId = params.id;

  const [run, setRun] = useState<OrderRun | null>(null);
  const [activities, setActivities] = useState<ActivityLog[]>([]);
  const [instruction, setInstruction] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const loadData = useCallback(async (showSpinner = false) => {
    if (showSpinner) setRefreshing(true);
    try {
      const [loadedRun, loadedActivities] = await Promise.all([
        api.getRun(runId),
        api.getRunActivities(runId),
      ]);
      setRun(loadedRun);
      setActivities(loadedActivities);
      setError(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Unable to load run.";
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [runId]);

  useEffect(() => {
    const initialLoad = async () => {
      await loadData();
    };

    void initialLoad();
    const interval = setInterval(() => {
      void loadData();
    }, 3000);
    return () => clearInterval(interval);
  }, [loadData]);

  const canSendToRun = run ? !["completed", "terminated", "failed", "terminating"].includes(run.status) : false;
  const isRunning = run?.status === "running";
  const isPaused = run?.status === "paused";

  const timelineCounts = useMemo(() => {
    const events = activities.filter((activity) => activity.activity_type === "event").length;
    const actions = activities.filter((activity) => activity.activity_type === "agent_action").length;
    const wakeups = activities.filter((activity) => activity.activity_type === "agent_wakeup").length;
    return { events, actions, wakeups };
  }, [activities]);

  const runAction = async (label: string, action: () => Promise<unknown>, success: string) => {
    setPendingAction(label);
    try {
      await action();
      setToast({ tone: "success", message: success });
      await loadData();
    } catch (err) {
      setToast({ tone: "error", message: err instanceof ApiError ? err.message : "Action failed." });
    } finally {
      setPendingAction(null);
    }
  };

  const handleSendEvent = (eventType: string, label: string) => {
    runAction(`event:${eventType}`, () => api.sendEvent(runId, eventType), `${label} sent.`);
  };

  const handleSendInstruction = async () => {
    const value = instruction.trim();
    if (!value) return;

    setPendingAction("instruction");
    try {
      await api.sendInstruction(runId, value);
      setInstruction("");
      setToast({ tone: "success", message: "Instruction delivered." });
      await loadData();
    } catch (err) {
      setToast({ tone: "error", message: err instanceof ApiError ? err.message : "Instruction could not be sent." });
    } finally {
      setPendingAction(null);
    }
  };

  if (loading) {
    return (
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-72 animate-pulse rounded-lg border border-border bg-white lg:col-span-2" />
        <div className="h-72 animate-pulse rounded-lg border border-border bg-white" />
      </div>
    );
  }

  if (!run) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
        {error || "Run could not be found."}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {toast && <Toast toast={toast} onDone={() => setToast(null)} />}

      <nav className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <Link href="/" className="flex items-center gap-1 transition hover:text-primary">
          <ArrowLeft className="size-3.5" />
          Orders
        </Link>
        <ChevronRight className="size-3.5" />
        <span className="font-medium text-foreground">{run.order_id}</span>
      </nav>

      <section className="flex flex-col gap-4 border-b border-border pb-5 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-normal text-foreground">{run.order_id}</h1>
            {statusBadge(run.status)}
          </div>
          <p className="truncate font-mono text-xs text-muted-foreground">{run.id}</p>
          <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="rounded-lg border border-border bg-white px-2.5 py-1">Sleep: {run.sleep_state}</span>
            <span className="rounded-lg border border-border bg-white px-2.5 py-1">Next wake: {formatDurationUntil(run.next_wake_at)}</span>
            <span className="rounded-lg border border-border bg-white px-2.5 py-1">Updated: {formatDateTime(run.updated_at)}</span>
          </div>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button variant="outline" className="gap-2" onClick={() => loadData(true)} disabled={refreshing}>
            <RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          {isRunning && (
            <Button
              variant="outline"
              className="gap-2"
              disabled={pendingAction === "pause"}
              onClick={() => runAction("pause", () => api.pauseRun(runId), "Run paused.")}
            >
              {pendingAction === "pause" ? <Loader2 className="size-4 animate-spin" /> : <CirclePause className="size-4" />}
              Pause
            </Button>
          )}
          {isPaused && (
            <Button
              variant="outline"
              className="gap-2"
              disabled={pendingAction === "resume"}
              onClick={() => runAction("resume", () => api.resumeRun(runId), "Run resumed.")}
            >
              {pendingAction === "resume" ? <Loader2 className="size-4 animate-spin" /> : <CirclePlay className="size-4" />}
              Resume
            </Button>
          )}
          {canSendToRun && (
            <Button
              variant="destructive"
              className="gap-2"
              disabled={pendingAction === "terminate"}
              onClick={() => runAction("terminate", () => api.terminateRun(runId), "Termination requested.")}
            >
              {pendingAction === "terminate" ? <Loader2 className="size-4 animate-spin" /> : <Square className="size-4 fill-current" />}
              Terminate
            </Button>
          )}
        </div>
      </section>

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-800">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <section className="grid gap-3 sm:grid-cols-3">
        {[
          { label: "Events", value: timelineCounts.events, icon: Bell },
          { label: "Agent wake-ups", value: timelineCounts.wakeups, icon: TimerReset },
          { label: "Tool actions", value: timelineCounts.actions, icon: TerminalSquare },
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

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <section className="space-y-4 lg:col-span-2">
          <Card className="rounded-lg border-border bg-white shadow-sm">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Activity className="size-4 text-primary" />
                Activity Timeline
                <span className="ml-auto text-xs font-normal text-muted-foreground">
                  {activities.length} item{activities.length === 1 ? "" : "s"}
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              {activities.length === 0 ? (
                <div className="flex min-h-56 flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/30 px-4 text-center">
                  <Clock className="size-5 text-muted-foreground" />
                  <h2 className="mt-3 text-sm font-semibold text-foreground">No activity recorded</h2>
                  <p className="mt-1 max-w-sm text-sm leading-6 text-muted-foreground">
                    The workflow will write wake-up, sleep, event, action, and final-output entries here.
                  </p>
                </div>
              ) : (
                <ol className="relative ml-3 border-l border-border">
                  {activities.map((activity) => {
                    const meta = activityMeta(activity);
                    const Icon = meta.icon;
                    const summary = activitySummary(activity);

                    return (
                      <li key={activity.id} className="relative pb-5 pl-6 last:pb-0">
                        <span className={`absolute -left-[13px] top-0 flex size-6 items-center justify-center rounded-full border bg-white ${meta.tone}`}>
                          <Icon className="size-3.5" />
                        </span>
                        <div className="rounded-lg border border-border bg-white p-4 shadow-sm">
                          <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                            <div>
                              <h3 className="text-sm font-semibold text-foreground">{meta.title}</h3>
                              <p className="mt-1 text-sm leading-6 text-muted-foreground">{summary}</p>
                            </div>
                            <time className="shrink-0 text-xs text-muted-foreground">{formatDateTime(activity.created_at)}</time>
                          </div>
                          <details className="mt-3">
                            <summary className="cursor-pointer text-xs font-medium text-primary">Details</summary>
                            <pre className="mt-2 max-h-64 overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 text-foreground">
                              {compactJson(activity.details)}
                            </pre>
                          </details>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardContent>
          </Card>
        </section>

        <aside className="space-y-4">
          {(run.final_summary || run.final_learnings || run.final_recommendations) && (
            <Card className="rounded-lg border-emerald-200 bg-emerald-50/60 shadow-sm">
              <CardHeader className="border-b border-emerald-200 pb-3">
                <CardTitle className="flex items-center gap-2 text-base font-semibold text-emerald-950">
                  <ClipboardList className="size-4" />
                  Final Output
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4 pt-4 text-sm leading-6 text-emerald-950">
                {run.final_summary && <p>{run.final_summary}</p>}
                {run.final_learnings && (
                  <div>
                    <h3 className="font-semibold">Learnings</h3>
                    <p className="mt-1 whitespace-pre-wrap">{run.final_learnings}</p>
                  </div>
                )}
                {run.final_recommendations && (
                  <div>
                    <h3 className="font-semibold">Recommendations</h3>
                    <p className="mt-1 whitespace-pre-wrap">{run.final_recommendations}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card className="rounded-lg border-border bg-white shadow-sm">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Brain className="size-4 text-primary" />
                Agent Memory
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-4">
              <p className="whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                {run.memory_summary || "Memory is empty until the agent processes the first wake-up."}
              </p>
            </CardContent>
          </Card>

          <Card className="rounded-lg border-border bg-white shadow-sm">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <Zap className="size-4 text-primary" />
                Inject Event
              </CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 gap-2 pt-4 sm:grid-cols-2 lg:grid-cols-1 xl:grid-cols-2">
              {ORDER_EVENTS.map((event) => (
                <Button
                  key={event.type}
                  variant={event.type === "delivered" ? "default" : "outline"}
                  size="sm"
                  disabled={!canSendToRun || pendingAction === `event:${event.type}`}
                  onClick={() => handleSendEvent(event.type, event.label)}
                  className="justify-start gap-2"
                >
                  {pendingAction === `event:${event.type}` ? <Loader2 className="size-3.5 animate-spin" /> : <Bell className="size-3.5" />}
                  <span className="truncate">{event.label}</span>
                </Button>
              ))}
            </CardContent>
          </Card>

          <Card className="rounded-lg border-border bg-white shadow-sm">
            <CardHeader className="border-b border-border pb-3">
              <CardTitle className="flex items-center gap-2 text-base font-semibold">
                <MessageSquare className="size-4 text-primary" />
                Instruction
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 pt-4">
              <Textarea
                value={instruction}
                onChange={(event) => setInstruction(event.target.value)}
                placeholder="Prioritize speed over cost if the shipment is delayed."
                rows={4}
                maxLength={2000}
                className="resize-none"
                disabled={!canSendToRun}
              />
              <Button
                className="w-full gap-2"
                onClick={handleSendInstruction}
                disabled={!canSendToRun || !instruction.trim() || pendingAction === "instruction"}
              >
                {pendingAction === "instruction" ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
                Send instruction
              </Button>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
