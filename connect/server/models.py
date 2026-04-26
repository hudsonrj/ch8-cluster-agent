from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
import time


class NodeRegisterRequest(BaseModel):
    node_id:      str
    network_id:   str
    address:      str
    port:         int = 7878
    hostname:     str = ""
    os:           str = ""
    arch:         str = ""
    capabilities: List[str] = []
    models:       List[str] = []   # LLM models available on this node
    version:      str = ""


class AgentInfo(BaseModel):
    name:     str
    status:   str = "running"   # running | idle | error
    task:     str = ""
    model:    str = ""          # model being used by this agent
    platform: str = ""          # ollama | openai | groq | etc.
    autonomous: bool = False
    alerts:           int = 0
    security_findings: int = 0
    predictions:      int = 0
    heavy_procs:      int = 0
    details:  Dict[str, Any] = {}
    updated_at: int = 0


class NodeHeartbeatRequest(BaseModel):
    node_id:    str
    network_id: str
    ts:         int = Field(default_factory=lambda: int(time.time()))
    cpu_pct:    float = 0.0
    mem_pct:    float = 0.0
    disk_pct:   float = 0.0
    agents:     List[AgentInfo] = []
    models:     List[str] = []
    services:   List[Dict[str, Any]] = []


class NodeInfo(BaseModel):
    node_id:       str
    network_id:    str
    address:       str
    port:          int
    hostname:      str
    os:            str
    arch:          str
    capabilities:  List[str]
    models:        List[str] = []
    version:       str
    status:        str
    last_seen:     int
    registered_at: int
    cpu_pct:       float = 0.0
    mem_pct:       float = 0.0
    disk_pct:      float = 0.0
    agents:        List[Dict[str, Any]] = []


class PreauthTokenCreate(BaseModel):
    network_id: str
    label:      str = ""
    ttl_hours:  int = 168


class PreauthTokenUse(BaseModel):
    token:   str
    node_id: str


class DeviceCodeRequest(BaseModel):
    node_id: str


class DeviceTokenPoll(BaseModel):
    grant_type:  str
    device_code: str


class ServiceInfo(BaseModel):
    type:   str = "process"   # docker | process
    name:   str
    image:  str = ""
    status: str = "running"
    ports:  str = ""
