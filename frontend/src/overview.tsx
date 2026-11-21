import { Activity, Bell, Database, Layers3, ShieldCheck, Workflow } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Link } from "react-router-dom";
import { api } from "./api";
import { Heading, integer, localDate, Metric, percent, Pill, State, storage } from "./components";

type Overview = {
  processed: number; runs: number; success_rate: number | null; active_sources: number; active_alerts: number;
  latest_publication: string | null; quality: number | null; storage: Record<string, number>;
  history: { run_id: string; date: string; status: string; seconds: number | null; processed: number; quality: number | null }[];
};
const tooltipStyle = { contentStyle: { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8 } };

export default function OverviewPage() {
  const query = useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/overview"), refetchInterval: 6000 });
  const monitor = useQuery({ queryKey: ["monitor"], queryFn: () => api<{datasets: {name: string; status: string}[]}>("/monitoring") });
  const data = query.data;
  const history = (data?.history ?? []).map((run, index) => ({ ...run, label: `Run ${index + 1}`, score: run.quality == null ? null : run.quality * 100 }));
  return <>
    <Heading title="Platform overview" description="Pipeline health, data quality and lakehouse activity in one workspace.">
      <Link className="button primary" to="/pipelines"><Workflow size={16}/> Manage pipelines</Link>
    </Heading>
    <State loading={query.isPending} error={query.error}>{data && <>
      <div className="metric-grid">
        <Metric title="Processed records" value={integer(data.processed)} detail="Across recorded runs" icon={<Database size={18}/>}/>
        <Metric title="Pipeline success" value={percent(data.success_rate)} detail={`${integer(data.runs)} recorded runs`} icon={<Workflow size={18}/>}/>
        <Metric title="Publication quality" value={percent(data.quality)} detail="Accepted rows in latest snapshot" icon={<ShieldCheck size={18}/>}/>
        <Metric title="Active alerts" value={integer(data.active_alerts)} detail={`${data.active_sources} active data sources`} icon={<Bell size={18}/>}/>
      </div>
      <div className="main-grid">
        <section className="panel chart"><div className="panel-title"><div><h2>Processing volume</h2><p>Records evaluated by run</p></div><Activity size={19}/></div>
          {history.length ? <ResponsiveContainer width="100%" height={230}><AreaChart data={history}>
            <CartesianGrid stroke="var(--line)" vertical={false}/>
            <XAxis dataKey="label" tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" />
            <YAxis tick={{ fill: "var(--muted)", fontSize: 12 }} stroke="var(--line)" width={52}/>
            <Tooltip {...tooltipStyle}/><Area name="Records" dataKey="processed" type="monotone" fill="var(--selected)" stroke="var(--accent)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false}/>
          </AreaChart></ResponsiveContainer> : <div className="empty">Run the pipeline to collect volume history.</div>}
        </section>
        <section className="panel"><div className="panel-title"><div><h2>Lakehouse storage</h2><p>Published Parquet data</p></div><Layers3 size={19}/></div>
          {Object.entries(data.storage).map(([zone, size]) => <div className="storage-row" key={zone}>
            <span className={`zone-dot ${zone}`}/><span>{zone}</span><strong>{storage(size)}</strong>
          </div>)}
          <div className="last-publish"><small>Latest publication</small><div>{localDate(data.latest_publication)}</div></div>
        </section>
      </div>
      <div className="main-grid">
        <section className="panel"><div className="panel-title"><div><h2>Recent runs</h2><p>Execution status and duration</p></div><Link to="/pipelines">All runs</Link></div>
          {history.length ? [...history].reverse().slice(0, 5).map(run => <Link to={`/pipelines?run=${run.run_id}`} className="run-row" key={run.run_id}>
            <span className="mono">{run.run_id.slice(0, 8)}</span><Pill value={run.status}/><span>{localDate(run.date)}</span>
            <strong>{run.seconds == null ? "—" : `${run.seconds.toFixed(1)} s`}</strong>
          </Link>) : <div className="empty">No runs have been recorded.</div>}
        </section>
        <section className="panel chart"><div className="panel-title"><div><h2>Quality trend</h2><p>Accepted share of evaluated rows</p></div></div>
          {history.some(run => run.score != null) ? <ResponsiveContainer width="100%" height={170}><LineChart data={history}>
            <CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="label" tick={{fill:"var(--muted)", fontSize: 11}}/>
            <YAxis domain={[0,100]} tickFormatter={v => `${v}%`} tick={{ fill: "var(--muted)", fontSize: 11 }} width={42}/>
            <Tooltip {...tooltipStyle}/><Line dataKey="score" name="Quality %" stroke="#43d5af" strokeWidth={2} dot={{r:4}} connectNulls isAnimationActive={false}/>
          </LineChart></ResponsiveContainer> : <div className="empty">Quality history will appear after validation.</div>}
        </section>
      </div>
      <section className="panel"><div className="panel-title"><div><h2>Dataset health</h2><p>Based on committed ingestion activity</p></div></div>
        <State loading={monitor.isPending} error={monitor.error}>
          <div className="tags">{monitor.data?.datasets.map(feed => <span className="dataset-tag" key={feed.name}>{feed.name}<Pill value={feed.status}/></span>)}</div>
        </State>
      </section>
    </>}</State>
  </>;
}
