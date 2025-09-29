# lb/lb.py
import asyncio, json, os, time, typing as t
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
import httpx
import math

CONFIG_PATH = os.getenv("LB_CONFIG", "/etc/lb/targets.json")
PROBE_INTERVAL = float(os.getenv("LB_PROBE_INTERVAL", "2.5"))  # seconds
TIMEOUT = float(os.getenv("LB_TIMEOUT", "1.5"))                 # per-probe timeout
ALPHA = float(os.getenv("LB_EWMA_ALPHA", "0.3"))                # EWMA smoothing

@dataclass
class Target:
    url: str                          # e.g., http://172.31.1.23:8000/cluster1
    ewma_ms: float = 5000.0
    healthy: bool = False
    last_ms: float = 9999.0
    last_ok: float = 0.0
    failures: int = 0

@dataclass
class ClusterState:
    name: str
    targets: list[Target] = field(default_factory=list)

class LBState:
    def __init__(self, cfg: dict[str, list[str]]):
        self.clusters: dict[str, ClusterState] = {}
        for name, urls in cfg.items():
            self.clusters[name] = ClusterState(
                name=name,
                targets=[Target(url=u) for u in urls]
            )
        self._lock = asyncio.Lock()
        self._stop = False

    async def probe_once(self, client: httpx.AsyncClient, tgt: Target):
        t0 = time.perf_counter()
        try:
            r = await client.get(tgt.url, timeout=TIMEOUT)
            ok = (200 <= r.status_code < 500)  # treat 4xx as up for lb selection
            dt = (time.perf_counter() - t0) * 1000.0
            if ok:
                tgt.last_ms = dt
                tgt.ewma_ms = ALPHA * dt + (1.0 - ALPHA) * tgt.ewma_ms
                tgt.healthy = True
                tgt.last_ok = time.time()
                tgt.failures = 0
            else:
                tgt.failures += 1
                tgt.healthy = False
                tgt.ewma_ms = min(9999.0, tgt.ewma_ms * 1.5)
        except Exception:
            tgt.failures += 1
            tgt.healthy = False
            tgt.ewma_ms = min(9999.0, tgt.ewma_ms * 1.5)

    async def run_prober(self):
        async with httpx.AsyncClient() as client:
            while not self._stop:
                async with self._lock:
                    groups = list(self.clusters.values())
                tasks = []
                for g in groups:
                    for tgt in g.targets:
                        tasks.append(self.probe_once(client, tgt))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                await asyncio.sleep(PROBE_INTERVAL)

    async def pick_fastest(self, cluster: str) -> Target:
        async with self._lock:
            g = self.clusters.get(cluster)
            if not g or not g.targets:
                raise HTTPException(503, f"No targets configured for {cluster}")
            healthy = [t for t in g.targets if t.healthy]
            candidates = healthy if healthy else g.targets
            # choose min ewma; tie-breaker last_ms
            best = min(candidates, key=lambda t: (t.ewma_ms, t.last_ms))
            return best

    async def snapshot(self):
        async with self._lock:
            out = {}
            for name, g in self.clusters.items():
                out[name] = [
                    {"url": t.url, "healthy": t.healthy, "ewma_ms": round(t.ewma_ms, 1),
                     "last_ms": round(t.last_ms, 1), "failures": t.failures,
                     "last_ok_s_ago": None if t.last_ok == 0 else round(time.time()-t.last_ok,1)}
                    for t in g.targets
                ]
            return out

def load_config(path: str) -> dict[str, list[str]]:
    with open(path, "r") as f:
        cfg = json.load(f)
    # sanity: only keep http urls
    for k, v in list(cfg.items()):
        cfg[k] = [u for u in v if u.startswith("http://")]
    return cfg

app = FastAPI()
state: LBState | None = None

@app.on_event("startup")
async def _startup():
    global state
    cfg = load_config(CONFIG_PATH)
    state = LBState(cfg)
    asyncio.create_task(state.run_prober())

@app.get("/status")
async def status():
    assert state is not None
    snap = await state.snapshot()
    return JSONResponse(snap)


async def forward(url: str) -> Response:
    try: # <--- ADD THIS
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=TIMEOUT)
            return Response(
                content=r.content,
                status_code=r.status_code,
                media_type=r.headers.get("content-type", "application/json")
            )
    except httpx.RequestError as e:
        # This catches connection errors, timeouts, etc.
        error_content = {"error": "Gateway Error", "detail": str(e)}
        return JSONResponse(status_code=503, content=error_content)


@app.get("/cluster1")
async def cluster1():
    assert state is not None
    tgt = await state.pick_fastest("cluster1")
    return await forward(tgt.url)

@app.get("/cluster2")
async def cluster2():
    assert state is not None
    tgt = await state.pick_fastest("cluster2")
    return await forward(tgt.url)
