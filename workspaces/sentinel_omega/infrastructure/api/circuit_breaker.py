from __future__ import annotations
import time, logging, threading
from dataclasses import dataclass
from typing import Callable, Optional, Dict
from functools import wraps
logger=logging.getLogger(__name__)
@dataclass
class CircuitConfig:
    failure_threshold: int=5
    recovery_timeout: float=60.0
    half_open_max_calls: int=3
    success_threshold: int=2
class CircuitBreaker:
    def __init__(self, name, config=None):
        self.name=name; self.config=config or CircuitConfig()
        self._failures=0; self._successes_half=0; self._state="CLOSED"; self._opened_at=None; self._half_calls=0; self._lock=threading.Lock()
    @property
    def state(self):
        with self._lock:
            if self._state=="OPEN" and self._opened_at and (time.time()-self._opened_at)>=self.config.recovery_timeout:
                self._state="HALF_OPEN"; self._half_calls=0; self._successes_half=0
                logger.info(f"[CB:{self.name}] OPEN->HALF_OPEN")
            return self._state
    def allow(self):
        s=self.state
        if s=="CLOSED": return True
        if s=="OPEN": return False
        with self._lock:
            if self._half_calls < self.config.half_open_max_calls:
                self._half_calls+=1; return True
            return False
    def record_success(self):
        with self._lock:
            if self._state=="HALF_OPEN":
                self._successes_half+=1
                if self._successes_half>=self.config.success_threshold:
                    self._state="CLOSED"; self._failures=0
                    logger.info(f"[CB:{self.name}] HALF_OPEN->CLOSED")
            elif self._state=="CLOSED": self._failures=max(0,self._failures-1)
    def record_failure(self):
        with self._lock:
            self._failures+=1
            if self._state=="HALF_OPEN":
                self._state="OPEN"; self._opened_at=time.time()
                logger.warning(f"[CB:{self.name}] HALF_OPEN->OPEN")
            elif self._state=="CLOSED" and self._failures>=self.config.failure_threshold:
                self._state="OPEN"; self._opened_at=time.time()
                logger.warning(f"[CB:{self.name}] CLOSED->OPEN ({self._failures} fails)")
_breakers={}
_lock=threading.Lock()
def get_breaker(name, config=None):
    with _lock:
        if name not in _breakers: _breakers[name]=CircuitBreaker(name,config)
        return _breakers[name]
def circuit(name, config=None):
    def deco(fn):
        br=get_breaker(name,config)
        @wraps(fn)
        def wrapper(*a,**kw):
            if not br.allow():
                logger.warning(f"[CB:{name}] blocked {fn.__name__} ({br.state})"); return None
            try:
                r=fn(*a,**kw); br.record_success(); return r
            except Exception:
                br.record_failure(); raise
        return wrapper
    return deco
