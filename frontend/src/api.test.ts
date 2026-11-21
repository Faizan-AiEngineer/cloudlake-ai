import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import { percent, storage } from "./components";

afterEach(() => vi.unstubAllGlobals());
describe("workspace API", () => {
  it("uses the versioned endpoint", async () => {
    const fetcher = vi.fn().mockResolvedValue({ok:true,json:async()=>({mode:"local"})});
    vi.stubGlobal("fetch",fetcher);
    await expect(api("/system/status")).resolves.toEqual({mode:"local"});
    expect(fetcher).toHaveBeenCalledWith("/api/v1/system/status",undefined);
  });
  it("surfaces the backend error", async () => {
    vi.stubGlobal("fetch",vi.fn().mockResolvedValue({ok:false,status:409,json:async()=>({detail:"Run in progress"})}));
    await expect(api("/runs",{method:"POST"})).rejects.toThrow("Run in progress");
  });
  it("formats sparse dashboard results", () => {
    expect(percent(null)).toBe("—");
    expect(percent(0)).toBe("0.0%");
    expect(storage(1024)).toBe("1.0 KB");
  });
});
