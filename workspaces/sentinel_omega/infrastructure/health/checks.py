from __future__ import annotations
import sqlite3, shutil, time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional
import logging
logger = logging.getLogger(__name__)
@dataclass
class CheckResult:
    name: str
    status: str
    message: str
    latency_ms: Optional[float] = None
    details: Dict = field(default_factory=dict)
@dataclass
class HealthStatus:
    healthy: bool
    timestamp: float
    version: str
    checks: List[CheckResult]
    summary: str
    def to_dict(self):
        return {"healthy": self.healthy, "timestamp": self.timestamp, "version": self.version, "summary": self.summary, "checks": [asdict(c) for c in self.checks]}
class HealthChecker:
    def __init__(self, db_path="/home/deamon/workspaces/sentinel_omega/data/SENTINEL_OMEGA_PRO.db", version="2.5.0-shadow-node"):
        self.db_path = Path(db_path)
        self.version = version
    def check_database(self):
        t0=time.time()
        try:
            if not self.db_path.exists():
                return CheckResult("database","warn",f"DB not found at {self.db_path}", latency_ms=(time.time()-t0)*1000)
            conn=sqlite3.connect(str(self.db_path), timeout=5)
            cur=conn.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 5")
            tables=[r[0] for r in cur.fetchall()]
            conn.close()
            return CheckResult("database","ok",f"DB ok {len(tables)} tables", latency_ms=(time.time()-t0)*1000, details={"tables":tables})
        except Exception as e:
            return CheckResult("database","fail",str(e), latency_ms=(time.time()-t0)*1000)
    def check_disk(self):
        try:
            usage=shutil.disk_usage(str(self.db_path.parent if self.db_path.parent.exists() else "."))
            pct=(usage.used/usage.total)*100
            status="ok" if pct<80 else "warn" if pct<90 else "fail"
            return CheckResult("disk",status,f"{pct:.1f}% used", details={"free_gb":round(usage.free/1e9,2)})
        except Exception as e:
            return CheckResult("disk","warn",str(e))
    def check_apis(self):
        t0=time.time()
        try:
            from sentinel_omega.infrastructure.api._http import get_session
            s=get_session()
            r=s.get("https://services.swpc.noaa.gov/json/planetary_k_index_1m.json", timeout=5)
            ok=r.status_code==200
            return CheckResult("apis","ok" if ok else "warn", f"NOAA {r.status_code}", latency_ms=(time.time()-t0)*1000)
        except Exception as e:
            return CheckResult("apis","warn",f"API fail: {e}", latency_ms=(time.time()-t0)*1000)
    def check_pipeline_staleness(self):
        try:
            if not self.db_path.exists():
                return CheckResult("pipeline","warn","DB missing")
            conn=sqlite3.connect(str(self.db_path), timeout=5)
            cur=conn.execute("SELECT MAX(ts) FROM tbl_salud_sistema")
            row=cur.fetchone()
            conn.close()
            if not row or row[0] is None:
                return CheckResult("pipeline","warn","No cycles yet")
            try:
                last=float(row[0])
            except Exception:
                from datetime import datetime
                last=datetime.fromisoformat(str(row[0]).replace("Z","+00:00")).timestamp()
            age_h=(time.time()-last)/3600
            status="ok" if age_h<2 else "warn" if age_h<6 else "fail"
            return CheckResult("pipeline",status,f"Last cycle {age_h:.1f}h ago", details={"age_hours":round(age_h,2)})
        except Exception as e:
            return CheckResult("pipeline","warn",str(e))
    def run_all(self):
        checks=[self.check_database(), self.check_disk(), self.check_apis(), self.check_pipeline_staleness()]
        healthy=all(c.status!="fail" for c in checks)
        fails=[c.name for c in checks if c.status=="fail"]
        warns=[c.name for c in checks if c.status=="warn"]
        if fails: summary="FAIL: " + ",".join(fails)
        elif warns: summary="WARN: " + ",".join(warns)
        else: summary="All systems nominal"
        return HealthStatus(healthy, time.time(), self.version, checks, summary)
def get_health():
    return HealthChecker().run_all().to_dict()
if __name__=="__main__":
    import json; print(json.dumps(get_health(), indent=2, ensure_ascii=False))
