"""
transport/ws_server.py
═══════════════════════
WebSocket server — streams live Nexus data to the dashboard.
Protocol: JSON messages with a `type` field.
"""

import asyncio
import json
import os
import secrets
import time
from pathlib import Path

import websockets
from websockets.server import WebSocketServerProtocol


def _session_key_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    p = Path(base) / "NexusFabric"
    p.mkdir(parents=True, exist_ok=True)
    return p / "session.key"


class NexusWebSocketServer:
    """
    Listens on ws://localhost:9001
    Broadcasts to all connected dashboard clients.

    Message types sent to clients:
      { type: "hardware",     data: {...} }   — every 0.5s
      { type: "agents",       data: [...] }   — every 3s
      { type: "cycle",        data: {...} }   — after each reasoning cycle
      { type: "log",          data: {...} }   — real-time log entries
      { type: "system_state", data: {...} }   — state summary

    Messages received from clients:
      { type: "set_profile",  profile: "BALANCED" }
      { type: "inject",       process: "game.exe" }
      { type: "get_agents" }
    """

    HOST = "localhost"
    PORT = 9001

    AUTH_TIMEOUT_SECONDS = 5

    def __init__(self):
        self._clients: set[WebSocketServerProtocol] = set()
        self._latest_hardware: dict = {}
        self._latest_agents:   list = []
        self._latest_cycle:    dict = {}
        self._log_queue:       list = []
        self._running          = False
        self._command_handler  = None
        self._session_token    = secrets.token_urlsafe(32)
        key_path = _session_key_path()
        key_path.write_text(self._session_token, encoding="utf-8")
        print(f"[WebSocket] Session token written to {key_path}")
        self._perf_state       = {
            "fps": 0, "frametime_ms": 0, "fps_1pct": 0,
            "ft_stddev": 0, "active_profile": "BALANCED"
        }

    def on_command(self, handler):
        """Register async handler for commands from dashboard: handler(cmd, data) -> result"""
        self._command_handler = handler

    # ─── Start / Stop ─────────────────────────────────────────────

    async def start(self):
        self._running = True
        server = await websockets.serve(
            self._handle_client,
            self.HOST,
            self.PORT,
            ping_interval=20,
            ping_timeout=10,
        )
        print(f"[WebSocket] Server running at ws://{self.HOST}:{self.PORT}")
        # Start broadcast loops
        asyncio.create_task(self._broadcast_hardware_loop())
        asyncio.create_task(self._broadcast_agents_loop())
        await server.wait_closed()

    # ─── Client Handler ───────────────────────────────────────────

    async def _authenticate(self, ws: WebSocketServerProtocol) -> bool:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=self.AUTH_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            await ws.close(code=4401, reason="auth_timeout")
            return False
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            await ws.close(code=4400, reason="auth_bad_frame")
            return False
        token = payload.get("auth") if isinstance(payload, dict) else None
        if not token or not secrets.compare_digest(str(token), self._session_token):
            await ws.close(code=4403, reason="auth_rejected")
            return False
        return True

    async def _handle_client(self, ws: WebSocketServerProtocol, path: str = "/"):
        if not await self._authenticate(ws):
            print("[WebSocket] Client rejected (auth)")
            return
        self._clients.add(ws)
        print(f"[WebSocket] Client connected — total: {len(self._clients)}")

        # Send current state immediately on connect
        await self._send(ws, "hardware",     self._latest_hardware)
        await self._send(ws, "agents",       self._latest_agents)
        await self._send(ws, "system_state", self._build_system_state())

        try:
            async for raw in ws:
                await self._handle_message(ws, raw)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)
            print(f"[WebSocket] Client disconnected — total: {len(self._clients)}")

    async def _handle_message(self, ws: WebSocketServerProtocol, raw: str):
        try:
            msg = json.loads(raw)
            mtype = msg.get("type")

            if mtype == "get_agents":
                await self._send(ws, "agents", self._latest_agents)

            elif mtype == "get_processes":
                procs = []
                if self._command_handler:
                    try:
                        res = await self._command_handler("get_processes", {})
                        procs = res if isinstance(res, list) else []
                    except Exception as e:
                        print(f"[WebSocket] get_processes error: {e}")
                await self._send(ws, "processes", procs)

            elif mtype == "set_profile":
                profile = msg.get("profile", "BALANCED")
                self._perf_state["active_profile"] = profile
                if self._command_handler:
                    await self._command_handler("set_profile", {"profile": profile})
                await self._broadcast("log", {
                    "source": "Execution Supervisor", "message": f"Quality profile transitioned to {profile}",
                    "level": "agent", "timestamp": time.time()
                })

            elif mtype == "inject":
                process = msg.get("process", "unknown")
                options = msg.get("options", {})
                res = None
                if self._command_handler:
                    res = await self._command_handler("inject", {"process": process, "options": options})
                status_msg = res.get("message", f"Injection active for: {process}") if isinstance(res, dict) else f"Injection initiated for {process}"
                await self._broadcast("log", {
                    "source": "Execution Supervisor",
                    "message": status_msg,
                    "level": "agent", "timestamp": time.time()
                })

            elif mtype == "rollback":
                res = None
                if self._command_handler:
                    res = await self._command_handler("rollback", {})
                msg_text = res.get("message", "Rollback executed successfully") if isinstance(res, dict) else "All configurations rolled back"
                await self._broadcast("log", {
                    "source": "Failsafe Commander",
                    "message": f"⚡ ROLLBACK: {msg_text}",
                    "level": "warn", "timestamp": time.time()
                })

            elif mtype == "ping":
                await self._send(ws, "pong", {"ts": time.time()})

        except (json.JSONDecodeError, Exception) as e:
            print(f"[WebSocket] Message error: {e}")

    # ─── Broadcast Loops ──────────────────────────────────────────

    async def _broadcast_hardware_loop(self):
        """Push hardware data every 500ms."""
        while self._running:
            if self._latest_hardware and self._clients:
                payload = {
                    **self._latest_hardware,
                    **self._perf_state,
                    "client_count": len(self._clients),
                    "sim_mode": False,
                }
                await self._broadcast("hardware", payload)
            await asyncio.sleep(0.5)

    async def _broadcast_agents_loop(self):
        """Push agent states every 3s."""
        while self._running:
            if self._latest_agents and self._clients:
                await self._broadcast("agents", self._latest_agents)
            await asyncio.sleep(3.0)

    # ─── Update Hooks (called by engine) ──────────────────────────

    def update_hardware(self, snapshot_dict: dict):
        """Called by HardwareDetector on every tick."""
        self._latest_hardware = snapshot_dict
        # Extract perf fields if present
        for key in ["fps", "frametime_ms", "fps_1pct", "ft_stddev"]:
            if key in snapshot_dict:
                self._perf_state[key] = snapshot_dict[key]

    def update_agents(self, agents_state: list):
        """Called by AgentCouncil."""
        self._latest_agents = agents_state

    def push_cycle(self, cycle_dict: dict):
        """Called when a reasoning cycle completes."""
        self._latest_cycle = cycle_dict
        asyncio.create_task(self._broadcast("cycle", cycle_dict))
        # Push cycle logs
        for log_entry in cycle_dict.get("logs", []):
            asyncio.create_task(self._broadcast("log", {
                **log_entry,
                "timestamp": log_entry.get("ts", time.time()),
            }))

    def push_log(self, source: str, message: str, level: str = "info"):
        """Push a single log entry to all clients."""
        entry = {"source": source, "message": message, "level": level, "timestamp": time.time()}
        self._log_queue.append(entry)
        if len(self._log_queue) > 500:
            self._log_queue.pop(0)
        asyncio.create_task(self._broadcast("log", entry))

    def set_perf(self, fps: float, frametime_ms: float, fps_1pct: float, stddev: float):
        """Update performance state (called by a future ETW reader)."""
        self._perf_state.update({
            "fps": round(fps, 1),
            "frametime_ms": round(frametime_ms, 2),
            "fps_1pct": round(fps_1pct, 1),
            "ft_stddev": round(stddev, 2),
        })

    # ─── Helpers ──────────────────────────────────────────────────

    async def _broadcast(self, msg_type: str, data):
        if not self._clients:
            return
        payload = json.dumps({"type": msg_type, "data": data, "ts": time.time()})
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send(payload)
            except websockets.exceptions.ConnectionClosed:
                dead.add(ws)
        self._clients -= dead

    async def _send(self, ws: WebSocketServerProtocol, msg_type: str, data):
        try:
            await ws.send(json.dumps({"type": msg_type, "data": data, "ts": time.time()}))
        except websockets.exceptions.ConnectionClosed:
            self._clients.discard(ws)

    def _build_system_state(self) -> dict:
        hw = self._latest_hardware
        return {
            "nexus_version":   "0.9",
            "agents_online":   len(self._latest_agents),
            "cycle_count":     self._latest_cycle.get("cycle_id", 0),
            "system_state":    self._latest_cycle.get("system_state", "INITIALIZING"),
            "system_health":   self._latest_cycle.get("system_health", 100),
            "active_profile":  self._perf_state.get("active_profile", "BALANCED"),
            "bottleneck":      hw.get("bottleneck", "UNKNOWN"),
            "active_game":     hw.get("active_game"),
            "ws_clients":      len(self._clients),
        }
