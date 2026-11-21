import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Cloud, Download, Play, Send } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "./api";
import { DataTable, Heading, human, integer, Listing, localDate, Metric, Pill, Row, State } from "./components";

type Run = { id: string; status: string; mode: string; started_at: string; duration: number | null; processed: number; rejected: number; error: string | null };
type RunDetail = { run: Run; tasks: Row[] };
const terminal = ["successful", "failed", "blocked"];

export function PipelinesPage() {
  const [params, setParams] = useSearchParams();
  const [mode, setMode] = useState<"batch"|"incremental">("batch");
  const [status, setStatus] = useState("");
  const [generate, setGenerate] = useState(false);
  const [offset, setOffset] = useState(0);
  const cache = useQueryClient();
  const runList = useQuery({
    queryKey: ["runs", status, offset],
    queryFn: () => api<Listing<Run>>(`/runs?limit=12&offset=${offset}${status ? `&status=${status}` : ""}`),
    refetchInterval: 4000,
  });
  const selected = params.get("run") ?? runList.data?.items[0]?.id;
  const detail = useQuery({ queryKey: ["run", selected], queryFn: () => api<RunDetail>(`/runs/${selected}`),
    enabled: !!selected, refetchInterval: query => terminal.includes(query.state.data?.run.status ?? "") ? false : 3500 });
  const log = useQuery({ queryKey: ["log", selected], queryFn: () => api<{log:string;available:boolean}>(`/runs/${selected}/logs`), enabled: !!selected, refetchInterval: 6000 });
  const submit = useMutation({
    mutationFn: (options: { mode: string; generate: boolean }) => api<{run_id:string}>("/runs", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(options),
    }),
    onSuccess: result => { setParams({run:result.run_id}); void cache.invalidateQueries({queryKey:["runs"]}); },
  });
  const active = runList.data?.items.some(item => !terminal.includes(item.status));
  return <>
    <Heading title="Pipeline manager" description="Trigger workspace jobs and follow each task from source discovery to Gold publication."/>
    <section className="panel"><h2>Start a run</h2>
      <form className="controls" onSubmit={e => { e.preventDefault(); submit.mutate({mode, generate}); }}>
        <label className="control">Execution mode<select value={mode} onChange={e => setMode(e.target.value as typeof mode)}>
          <option value="batch">Full batch</option><option value="incremental">Incremental</option></select></label>
        <label className="check"><input type="checkbox" checked={generate} onChange={e=>setGenerate(e.target.checked)}/> Generate demo sources first</label>
        <button className="primary" disabled={submit.isPending || active}><Play size={16}/> Start run</button>
      </form>
      {submit.isError && <p className="error" role="alert">{submit.error.message}</p>}
    </section>
    <div className="two-column">
      <section className="panel">
        <div className="panel-title"><div><h2>Run history</h2><p>{runList.data?.total ?? 0} recorded runs</p></div>
          <select aria-label="Filter runs" value={status} onChange={e=>{setStatus(e.target.value);setOffset(0);}}>
            <option value="">All statuses</option>{["successful","running","pending","failed","blocked"].map(item=><option key={item} value={item}>{human(item)}</option>)}
          </select>
        </div>
        <State loading={runList.isPending} error={runList.error}>
          {runList.data?.items.length ? runList.data.items.map(item => <button key={item.id}
            className={`source-row ${selected === item.id ? "selected" : ""}`} onClick={()=>setParams({run:item.id})}>
            <span className="mono">{item.id.slice(0,8)}</span><span><strong>{human(item.mode)}</strong><small>{localDate(item.started_at)}</small></span><Pill value={item.status}/>
          </button>) : <div className="empty">Start a pipeline to create a run record.</div>}
          <div className="controls pagination"><button disabled={!offset} onClick={()=>setOffset(offset - 12)}>Previous</button>
            <button disabled={offset + 12 >= (runList.data?.total ?? 0)} onClick={()=>setOffset(offset + 12)}>Next</button></div>
        </State>
      </section>
      <section className="panel">
        <h2>Execution timeline</h2>
        {selected ? <State loading={detail.isPending} error={detail.error}>{detail.data && <>
          <div className="controls"><span className="mono">{detail.data.run.id.slice(0,8)}</span><Pill value={detail.data.run.status}/>
            <span className="muted">{integer(detail.data.run.processed)} processed · {integer(detail.data.run.rejected)} rejected</span></div>
          {detail.data.run.error && <p role="alert" className="error">{detail.data.run.error}</p>}
          <ol className="timeline">{detail.data.tasks.map((task, index)=><li key={index}><div>
            <strong>{human(String(task.name))}</strong><small>{String(task.message ?? "")}</small></div><Pill value={String(task.status)}/>
            <span className="muted">{task.seconds == null ? "—" : `${Number(task.seconds).toFixed(1)} s`}</span>
          </li>)}</ol>
        </>}</State> : <div className="empty">Select a run to see its recorded tasks.</div>}
      </section>
    </div>
    {selected && <section className="panel"><h2>Worker log</h2><State loading={log.isPending} error={log.error}>
      {log.data?.available ? <pre className="log">{log.data.log || "Waiting for worker output…"}</pre> : <div className="empty">The selected run has task messages only.</div>}
    </State></section>}
  </>;
}

type AssistantResponse = { answer: string; evidence: {label:string;path:string}[]; actions: string[]; supported:boolean;confidence:string };
const prompts = ["Why did the last pipeline fail?", "Which dataset has the lowest quality score?",
  "Are there any stale datasets?", "How has revenue changed this month?"];
export function AssistantPage() {
  const [input, set] = useState("");
  const [messages, add] = useState<{question:string;result:AssistantResponse}[]>([]);
  const provider = useQuery({ queryKey:["provider"], queryFn:()=>api<{provider:string;available:boolean}>("/assistant/status") });
  const ask = useMutation({
    mutationFn: (question: string) => api<AssistantResponse>("/assistant/ask", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question}),
    }), onSuccess:(result, question)=>add(current=>[...current, {question,result}]),
  });
  function send(value: string) {
    if (value.trim().length < 3 || ask.isPending) return;
    ask.mutate(value.trim()); set("");
  }
  return <>
    <Heading title="AI operations assistant" description="Ask about published analytics, run failures, quality checks and dataset freshness.">
      <Pill value={provider.isError ? "missing" : provider.data?.available ? "offline" : "pending"}/>
    </Heading>
    <section className="panel assistant">
      <div className="prompt-grid">{prompts.map(question=><button key={question} disabled={ask.isPending} onClick={()=>send(question)}>{question}</button>)}</div>
      <div className="conversation" aria-live="polite">
        {!messages.length && <div className="empty">Choose a question or ask about this workspace.</div>}
        {messages.map(({question,result},index)=><article key={index}>
          <div className="message user">{question}</div>
          <div className="message answer"><small>{human(result.confidence)}</small><p>{result.answer}</p>
            {result.actions.length > 0 && <ul>{result.actions.map(action=><li key={action}>{action}</li>)}</ul>}
            <div className="tags">{result.evidence.map(ref=><Link key={ref.path} to={ref.path}>{ref.label}</Link>)}</div>
          </div>
        </article>)}
        {ask.isPending && <p role="status" className="muted">Querying workspace data…</p>}
        {ask.error && <p role="alert" className="error">{ask.error.message}</p>}
      </div>
      <form className="composer" onSubmit={e=>{e.preventDefault();send(input);}}>
        <input value={input} onChange={e=>set(e.target.value)} aria-label="Operational question" placeholder="Ask an operational question" maxLength={400}/>
        <button className="primary" disabled={ask.isPending || input.trim().length < 3}><Send size={16}/> Ask</button>
      </form>
    </section>
  </>;
}

type Alert = {id:number;run_id:string|null;kind:string;status:string;severity:string;message:string;created_at:string};
export function AlertsPage() {
  const [status, setStatus] = useState("");
  const [severity, setSeverity] = useState("");
  const params = new URLSearchParams();
  if (status) params.set("status",status);
  if (severity) params.set("severity",severity);
  const cache = useQueryClient();
  const query = useQuery({queryKey:["alerts",status,severity],queryFn:()=>api<Listing<Alert>>(`/alerts?${params}`)});
  const datasets = useQuery({queryKey:["monitor"],queryFn:()=>api<{datasets:Row[]}>("/monitoring")});
  const update = useMutation({
    mutationFn: ({id,status}: {id:number;status:string})=>api(`/alerts/${id}`, {method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})}),
    onSuccess: ()=>void cache.invalidateQueries({queryKey:["alerts"]}),
  });
  return <>
    <Heading title="Alerts & monitoring" description="Acknowledge incidents and check ingestion freshness."/>
    <section className="panel">
      <div className="panel-title"><div><h2>Alert history</h2><p>{query.data?.total ?? 0} matching alerts</p></div>
        <div className="controls">
          <select aria-label="Alert status" value={status} onChange={e=>setStatus(e.target.value)}><option value="">All statuses</option>
            {["open","acknowledged","resolved"].map(item=><option key={item} value={item}>{human(item)}</option>)}</select>
          <select aria-label="Severity" value={severity} onChange={e=>setSeverity(e.target.value)}><option value="">All severities</option>
            {["CRITICAL","WARNING","INFO"].map(item=><option key={item}>{item}</option>)}</select>
        </div>
      </div>
      {update.error && <p className="error" role="alert">{update.error.message}</p>}
      <State loading={query.isPending} error={query.error}>
        {query.data?.items.length ? query.data.items.map(item=><article key={item.id} className="alert-row">
          <div><strong>{human(item.kind)}</strong><p>{item.message}</p><small>{localDate(item.created_at)} {item.run_id && <Link to={`/pipelines?run=${item.run_id}`}> · View run</Link>}</small></div>
          <div className="controls"><Pill value={item.severity}/><Pill value={item.status}/></div>
          <div className="controls">{item.status === "open" && <button onClick={()=>update.mutate({id:item.id,status:"acknowledged"})} disabled={update.isPending}>Acknowledge</button>}
            {item.status !== "resolved" && <button onClick={()=>update.mutate({id:item.id,status:"resolved"})} disabled={update.isPending}>Resolve</button>}</div>
        </article>) : <div className="empty">No alerts match these filters.</div>}
      </State>
    </section>
    <section className="panel"><h2>Dataset freshness</h2><State loading={datasets.isPending} error={datasets.error}><DataTable rows={datasets.data?.datasets ?? []}/></State></section>
  </>;
}

type System = {mode:string;api:string;metadata:{engine:string;available:boolean};aws_deployed:boolean};
export function InfrastructurePage() {
  const query = useQuery({queryKey:["infrastructure"],queryFn:()=>api<System>("/system/status")});
  return <>
    <Heading title="Cloud infrastructure" description="Local service health and the AWS data-plane deployment boundary."/>
    <State loading={query.isPending} error={query.error}>{query.data && <div className="metric-grid three">
      <Metric title="Execution mode" value={human(query.data.mode)} detail="Workspace deployment"/>
      <Metric title="Operational store" value={query.data.metadata.engine} detail={query.data.metadata.available ? "Connection healthy" : "Connection unavailable"} />
      <Metric title="AWS deployment" value={query.data.aws_deployed ? "Verified" : "Unverified"} detail="Cloud deployment status" icon={<Cloud size={18}/>}/>
    </div>}</State>
    <section className="panel"><h2>AWS architecture</h2>
      <DataTable rows={[
        { service:"Amazon S3", purpose:"Versioned source, pipeline and analytical storage", verification:"Infrastructure configuration" },
        { service:"AWS Glue", purpose:"Spark processing and Iceberg catalog", verification:"Deployment unverified" },
        { service:"Amazon Athena", purpose:"Bounded query workgroup", verification:"Deployment unverified" },
        { service:"EventBridge + SQS", purpose:"Landing events, schedules and retry queue", verification:"Deployment unverified" },
        { service:"AWS Lambda", purpose:"Validate events and request Glue runs", verification:"Deployment unverified" },
        { service:"CloudWatch", purpose:"Operational logs and queue alarms", verification:"Deployment unverified" },
      ]}/>
    </section>
    <section className="panel"><h2>Illustrative monthly estimate</h2>
      <p className="muted">US East (N. Virginia) · USD · Two services only</p>
      <DataTable rows={[
        { service:"AWS Glue", assumed_usage:"30 runs × 2 DPUs × 15 minutes", unit_rate:"$0.44 / DPU-hour", estimated_usd:(30 * 2 * .25 * .44).toFixed(2) },
        { service:"Amazon Athena", assumed_usage:"0.1 TB billed per month", unit_rate:"$5 / TB", estimated_usd:(.1 * 5).toFixed(2) },
      ]}/>
      <p className="muted">Allow separately for storage, requests, networking and monitoring. <a href="https://docs.aws.amazon.com/solutions/latest/guidance-for-multi-omics-and-multi-modal-data-integration-and-analysis-on-aws/cost.html">AWS example rates</a></p>
    </section>
  </>;
}

const reports = [
  ["executive","Executive platform report"],["pipeline","Pipeline performance"],["quality","Data quality"],
  ["business","Business analytics"],["infrastructure","Infrastructure configuration"],["incident","Operational incidents"],
];
export function ReportsPage() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  async function download(kind:string, format:string) {
    setError("");setBusy(kind+format);
    try {
      const response = await fetch(`/api/v1/reports/${kind}/${format}`);
      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? "Report generation failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href=url;anchor.download=`cloudlake-${kind}.${format}`;anchor.click();
      setTimeout(()=>URL.revokeObjectURL(url),1000);
    } catch (error) { setError(error instanceof Error ? error.message : "Report generation failed"); }
    finally { setBusy(""); }
  }
  return <>
    <Heading title="Reports" description="Generate exports from workspace records and published analytics."/>
    {error && <div className="panel error" role="alert">{error}</div>}
    <div className="report-grid">{reports.map(([kind,name])=><section className="panel report-card" key={kind}>
      <span className="report-icon"><Download size={20}/></span><h2>{name}</h2>
      <div className="controls">{["pdf","csv","xlsx"].map(format=><button key={format} disabled={!!busy} onClick={()=>void download(kind,format)} aria-label={`Download ${name} ${format.toUpperCase()}`}>
        {busy === kind+format ? "Preparing…" : format.toUpperCase()}</button>)}</div>
    </section>)}</div>
  </>;
}

export function SettingsPage() {
  const query = useQuery({queryKey:["settings"],queryFn:()=>api<Record<string,string|number>>("/system/configuration")});
  return <><Heading title="Settings" description="Inspect the running configuration. Use the top bar to change the console theme."/>
    <section className="panel"><h2>Workspace configuration</h2><State loading={query.isPending} error={query.error}>
      <DataTable rows={Object.entries(query.data ?? {}).map(([setting,value])=>({setting,value}))}/>
    </State></section></>;
}
