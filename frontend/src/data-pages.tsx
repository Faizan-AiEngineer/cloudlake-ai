import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Database, Upload, ZoomIn, ZoomOut } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "./api";
import { DataTable, Heading, human, integer, Listing, localDate, Metric, money, percent, Row, State, storage } from "./components";

type Field = { name: string; type: string };
type Source = {
  dataset: string; type: string; rows: number; updated_at: string | null; event_watermark: string | null;
  schema_version: string; schema: Record<string, string>; files: Row[];
};
type Preview = { rows: Row[]; total: number; bytes: number; fields: Field[]; partitions: string[] };

export function SourcesPage() {
  const [selected, select] = useState("orders");
  const [file, choose] = useState<File>();
  const list = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources") });
  const upload = useMutation({
    mutationFn: ({ dataset, input }: { dataset: string; input: File }) =>
      api<{ file: string }>(`/sources/${dataset}/upload?filename=${encodeURIComponent(input.name)}`, { method: "POST", body: input }),
  });
  const current = list.data?.find(row => row.dataset === selected);
  return <>
    <Heading title="Data sources" description="Inspect registered feeds, schemas and ingestion history."/>
    <State loading={list.isPending} error={list.error}><div className="two-column">
      <section className="panel"><h2>Registered feeds</h2>
        {list.data?.map(row => <button className={`source-row ${row.dataset === selected ? "selected" : ""}`} key={row.dataset} onClick={() => select(row.dataset)}>
          <Database size={18}/><span><strong>{human(row.dataset)}</strong><small>{row.type}</small></span><span>{integer(row.rows)} rows</span>
        </button>)}
      </section>
      <div className="stack"><section className="panel">
        <div className="panel-title"><div><h2>{human(selected)}</h2><p>Schema version {current?.schema_version} · Last ingested {localDate(current?.updated_at ?? null)}</p></div></div>
        <DataTable rows={Object.entries(current?.schema ?? {}).map(([column, type]) => ({ column, type }))}/>
      </section><section className="panel"><h2>Stage a source file</h2>
        <form className="controls" onSubmit={event => { event.preventDefault(); if (file) upload.mutate({dataset:selected, input:file}); }}>
          <input type="file" aria-label="Choose source file" accept=".csv,.json,.parquet" onChange={event => choose(event.target.files?.[0])}/>
          <button className="primary" disabled={!file || upload.isPending}><Upload size={16}/> Upload</button>
        </form>
        {upload.isError && <p role="alert" className="error">{upload.error.message}</p>}
        {upload.data && <p role="status">File staged. Start a pipeline run to ingest it.</p>}
      </section><section className="panel"><h2>Ingestion history</h2><DataTable rows={current?.files ?? []}/></section></div>
    </div></State>
  </>;
}

const zones = ["bronze", "silver", "gold", "quarantine"] as const;
type Zone = typeof zones[number];
export function LakehousePage() {
  const [zone, setZone] = useState<Zone>("gold");
  const [name, setName] = useState("");
  const catalog = useQuery({ queryKey: ["catalog"], queryFn: () => api<Record<Zone, string[]> & { published: boolean }>("/lakehouse") });
  const names = catalog.data?.[zone] ?? [];
  const selected = names.includes(name) ? name : names[0];
  const query = useQuery({ queryKey: ["preview", zone, selected], queryFn: () => api<Preview>(`/lakehouse/${zone}/${selected}`), enabled: !!selected });
  const iceberg = useQuery({ queryKey: ["iceberg"], queryFn: () => api<{available:boolean;table:string;schema_id:number;snapshots:Row[]}>("/iceberg/snapshots"), enabled: zone === "gold" });
  return <>
    <Heading title="Lakehouse explorer" description="Inspect partitions and records in each medallion layer."/>
    <State loading={catalog.isPending} error={catalog.error}><section className="panel">
      <div className="tabs">{zones.map(item => <button className={item === zone ? "selected" : ""} key={item} onClick={() => setZone(item)}>{human(item)}</button>)}</div>
      <label className="control">Dataset<select value={selected ?? ""} onChange={event => setName(event.target.value)}>
        {names.map(item => <option key={item}>{item}</option>)}
      </select></label>
    </section></State>
    {selected && <State loading={query.isPending} error={query.error}><div className="stack">
      <section className="panel"><div className="panel-title"><div><h2>Record preview</h2><p>{integer(query.data?.total ?? 0)} records · {storage(query.data?.bytes ?? 0)}</p></div></div>
        <DataTable rows={query.data?.rows ?? []}/>
      </section>
      <div className="two-column"><section className="panel"><h2>Schema</h2><DataTable rows={query.data?.fields ?? []}/></section>
        <section className="panel"><h2>Partitions</h2><DataTable rows={(query.data?.partitions ?? []).map(partition => ({ partition }))}/></section>
      </div>
    </div></State>}
    {zone === "gold" && iceberg.data?.available && <section className="panel">
      <div className="panel-title"><div><h2>Iceberg snapshot history</h2><p>{iceberg.data.table} · Schema {iceberg.data.schema_id}</p></div></div>
      <DataTable rows={iceberg.data.snapshots}/>
    </section>}
  </>;
}

export function QualityPage() {
  const [dataset, select] = useState("");
  const [offset, setOffset] = useState(0);
  const [run, selectRun] = useState("");
  const params = new URLSearchParams({ limit: "24", offset: String(offset) });
  if (dataset) params.set("dataset", dataset);
  if (run) params.set("run_id", run);
  const sources = useQuery({ queryKey: ["sources"], queryFn: () => api<Source[]>("/sources") });
  const runs = useQuery({ queryKey: ["runs"], queryFn: () => api<Listing<Row & {id:string;status:string}>>("/runs") });
  const query = useQuery({ queryKey: ["quality", params.toString()], queryFn: () => api<Listing<Row>>(`/quality?${params}`) });
  const quarantine = useQuery({ queryKey: ["quarantine", run], queryFn: () => api<Preview>(`/lakehouse/quarantine/rejected_records${run ? `?run_id=${run}` : ""}`) });
  return <>
    <Heading title="Data quality" description="Review rule evaluations, blocked runs and quarantined records."/>
    <section className="panel stack">
      <div className="controls">
        <label className="control">Dataset<select value={dataset} onChange={e => { select(e.target.value); setOffset(0); }}>
          <option value="">All datasets</option>{sources.data?.map(source => <option key={source.dataset}>{source.dataset}</option>)}
        </select></label>
        <label className="control">Pipeline run<select value={run} onChange={e => { selectRun(e.target.value); setOffset(0); }}>
          <option value="">All runs</option>{runs.data?.items.map(item => <option key={item.id} value={item.id}>{item.id.slice(0,8)} · {item.status}</option>)}
        </select></label>
      </div>
      <State loading={query.isPending} error={query.error}><DataTable rows={(query.data?.items ?? []).map(item => ({...item, pass_rate: percent(Number(item.pass_rate)), run: String(item.run_id).slice(0, 8)}))}
        columns={["dataset", "rule_name", "severity", "evaluated", "failed", "pass_rate", "status", "run"]}/>
        <div className="controls"><button disabled={offset === 0} onClick={() => setOffset(value => value - 24)}>Previous</button>
          <span className="muted">{query.data?.total ?? 0} evaluations</span>
          <button disabled={offset + 24 >= (query.data?.total ?? 0)} onClick={() => setOffset(value => value + 24)}>Next</button></div>
      </State>
    </section>
    <section className="panel"><h2>Quarantine</h2><State loading={quarantine.isPending} error={quarantine.error}>
      <DataTable rows={quarantine.data?.rows ?? []} columns={["dataset", "record_id", "reason", "source_file", "payload"]} empty="No quarantined records in the selected snapshot."/>
    </State></section>
  </>;
}

type Node = { id: string; name: string; zone: string };
type Edge = { source: string; target: string; origin: string };
export function LineagePage() {
  const [selected, setSelected] = useState("gold:fact_sales");
  const [zoom, setZoom] = useState(1);
  const query = useQuery({ queryKey: ["lineage"], queryFn: () => api<{nodes: Node[];edges: Edge[]}>("/lineage") });
  const zones = ["source", "bronze", "silver", "gold", "dashboard"];
  const positions = new Map<string, {x:number;y:number}>();
  for (const [index, zone] of zones.entries()) {
    query.data?.nodes.filter(node => node.zone === zone).forEach((node, row) => positions.set(node.id, {x: index * 188 + 8, y: 36 + row * 36}));
  }
  const linked = query.data?.edges.filter(edge => edge.source === selected || edge.target === selected) ?? [];
  const activeNodes = new Set([selected, ...linked.flatMap(edge => [edge.source, edge.target])]);
  return <>
    <Heading title="Data lineage" description="Explore declared relationships across the data platform.">
      <div className="controls"><button aria-label="Zoom out" onClick={() => setZoom(value => Math.max(.65, value - .15))}><ZoomOut size={17}/></button>
        <button aria-label="Zoom in" onClick={() => setZoom(value => Math.min(1.75, value + .15))}><ZoomIn size={17}/></button></div>
    </Heading>
    <State loading={query.isPending} error={query.error}>
      <section className="panel graph"><div className="graph-space" style={{width: 955 * zoom, height: 870 * zoom}}>
        <div className="graph-inner" style={{transform: `scale(${zoom})`}}>
          {zones.map((zone, index) => <strong className="graph-label" style={{left:index * 188 + 8}} key={zone}>{human(zone)}</strong>)}
          <svg className="edges" width="950" height="865" aria-hidden="true">
            {query.data?.edges.map(edge => {
              const from = positions.get(edge.source), to = positions.get(edge.target);
              if (!from || !to) return null;
              const x = from.x + 157, end = to.x, middle = (x + end) / 2;
              return <path key={edge.source+edge.target} className={linked.includes(edge) ? "linked" : ""}
                d={`M ${x} ${from.y+14} C ${middle} ${from.y+14}, ${middle} ${to.y+14}, ${end} ${to.y+14}`}/>;
            })}
          </svg>
          {query.data?.nodes.map(node => {
            const item = positions.get(node.id)!;
            return <button key={node.id} style={{left:item.x,top:item.y}} className={`graph-node ${activeNodes.has(node.id) ? "linked" : ""} ${selected === node.id ? "selected" : ""}`}
              onClick={() => setSelected(node.id)} aria-pressed={selected === node.id}>{human(node.name)}</button>;
          })}
        </div>
      </div></section>
      <section className="panel"><h2>{human(selected.split(":")[1] ?? "")}</h2><DataTable rows={linked.map(edge => ({ direction: edge.source === selected ? "Downstream" : "Upstream", dataset: edge.source === selected ? edge.target : edge.source, basis: edge.origin }))}/></section>
    </State>
  </>;
}

const criteria = ["start", "end", "country", "region", "category", "segment", "channel"];
type Analytics = { available: boolean; kpis: Record<string, number | null>; trend: Row[]; categories: Row[]; regions: Row[]; channels: Row[] };
export function AnalyticsPage() {
  const [filters, apply] = useState("");
  const [model, choose] = useState("inventory_performance");
  const query = useQuery({ queryKey: ["analytics", filters], queryFn: () => api<Analytics>(`/analytics?${filters}`) });
  const models = useQueryClient();
  const detail = useQuery({ queryKey: ["model", model], queryFn: () => api<Preview>(`/lakehouse/gold/${model}`), enabled: !!query.data?.available });
  const data = query.data;
  return <>
    <Heading title="Business analytics" description="Recognized sales, gross profit and commerce activity from the published snapshot."/>
    <form className="panel filter-grid" onSubmit={event => {
      event.preventDefault();
      const next = new URLSearchParams();
      for (const [key, value] of new FormData(event.currentTarget)) if (String(value).trim()) next.set(key, String(value).trim());
      apply(next.toString());
    }}>
      {criteria.map((item, index) => <label className="control" key={item}>{human(item)}<input name={item} type={index < 2 ? "date" : "text"} placeholder={index < 2 ? "" : "All"} maxLength={60}/></label>)}
      <div className="controls"><button className="primary">Apply</button><button type="reset" onClick={() => {apply(""); void models.invalidateQueries({queryKey:["analytics"]});}}>Reset</button></div>
    </form>
    <State loading={query.isPending} error={query.error}>{data?.available ?
      <>
        <div className="metric-grid">
          <Metric title="Revenue" value={money(data.kpis.revenue_usd)} detail="Completed, excluding tax"/>
          <Metric title="Gross profit" value={money(data.kpis.gross_profit_usd)} detail={`${percent(data.kpis.gross_margin)} margin`}/>
          <Metric title="Completed orders" value={integer(data.kpis.orders ?? 0)} detail={data.kpis.average_order_value == null ? "No completed orders" : `${money(data.kpis.average_order_value)} average value`}/>
          <Metric title="Active customers" value={integer(data.kpis.customers ?? 0)} detail={`${percent(data.kpis.repeat_rate)} repeat purchasing`}/>
        </div>
        <section className="panel"><div className="panel-title"><div><h2>Recognized revenue</h2><p>Monthly sales in USD</p></div></div>
          {data.trend.length ? <ResponsiveContainer width="100%" height={265}><BarChart data={data.trend}>
            <CartesianGrid stroke="var(--line)" vertical={false}/><XAxis dataKey="month" tickFormatter={value => String(value).slice(0,7)} tick={{fill:"var(--muted)",fontSize:11}}/>
            <YAxis tick={{fill:"var(--muted)",fontSize:11}}/><Tooltip contentStyle={{background:"var(--panel)",borderColor:"var(--line)"}}/><Bar name="Revenue" dataKey="revenue_usd" fill="#61aef5" radius={[3,3,0,0]} isAnimationActive={false}/>
          </BarChart></ResponsiveContainer> : <div className="empty">No sales match the selected filters.</div>}
        </section>
        <div className="two-column"><section className="panel"><h2>Product profitability</h2><DataTable rows={data.categories}/></section>
          <section className="panel"><h2>Regional performance</h2><DataTable rows={data.regions}/></section></div>
        <section className="panel"><h2>Marketing channels</h2><DataTable rows={data.channels}/></section>
        <section className="panel stack">
          <div className="panel-title"><div><h2>Published analytical models</h2><p>Snapshot-wide model previews</p></div></div>
          <label className="control">Model<select value={model} onChange={e=>choose(e.target.value)}>
            {["inventory_performance", "payment_success", "conversion_funnel", "customer_segmentation", "returns_cancellations", "revenue_growth"].map(item => <option value={item} key={item}>{human(item)}</option>)}
          </select></label>
          <State loading={detail.isPending} error={detail.error}><DataTable rows={detail.data?.rows ?? []}/></State>
        </section>
      </> : <div className="panel empty">Publish a pipeline run to start exploring business metrics.</div>}</State>
  </>;
}
