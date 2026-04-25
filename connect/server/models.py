"""
Pydantic models for the CH8 control server API.
"""

from typing import List, Optional
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
    version:      str = ""


class NodeHeartbeatRequest(BaseModel):
    node_id:    str
    network_id: str
    ts:         int = Field(default_factory=lambda: int(time.time()))
    cpu_pct:    float = 0.0
    mem_pct:    float = 0.0
    disk_pct:   float = 0.0


class NodeInfo(BaseModel):
    node_id:      str
    network_id:   str
    address:      str
    port:         int
    hostname:     str
    os:           str
    arch:         str
    capabilities: List[str]
    version:      str
    status:       str   # "online" | "offline"
    last_seen:    int
    registered_at: int


class PreauthTokenCreate(BaseModel):
    network_id: str
    label:      str = ""
    ttl_hours:  int = 168  # 7 days


class PreauthTokenUse(BaseModel):
    token:   str
    node_id: str


class DeviceCodeRequest(BaseModel):
    node_id: str


class DeviceTokenPoll(BaseModel):
    grant_type:  str
    device_code: str
