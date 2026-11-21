import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import "./style.css";

const query = new QueryClient({ defaultOptions: { queries: { retry: 1, staleTime: 10_000 } } });

class Boundary extends React.Component<React.PropsWithChildren, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (this.state.failed) return <main role="alert">The console encountered an error. <button onClick={() => location.reload()}>Reload</button></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><Boundary><QueryClientProvider client={query}><BrowserRouter><App /></BrowserRouter></QueryClientProvider></Boundary></React.StrictMode>,
);
