"""Sound for the Control Panel: outputs, inputs and their volume, through `pactl`. No GTK dependency.

`pactl` talks to PulseAudio and to PipeWire (through pipewire-pulse), so this covers every mainstream distribution.
Inputs leave out the "Monitor of …" sources PulseAudio makes for every output: they are not microphones."""
from __future__ import annotations
import re
from dataclasses import dataclass, field

from tvwcs.control_cmd import have, key_values, run

VOLUME_STEP=5      # percent per press of − / +
MAX_VOLUME=100     # pactl allows more (amplified, distorting); the panel stops at 100 %

@dataclass
class Port:
    name: str
    label: str
    available: bool = True

@dataclass
class Device:
    kind: str            # "sink" (an output) or "source" (an input)
    index: int
    name: str
    description: str
    volume: int          # percent, the average of the channels
    muted: bool
    ports: list = field(default_factory=list)
    active_port: str = ""
    is_monitor: bool = False
    icon: str = ""
    @property
    def label(self): return self.description or self.name

@dataclass
class SoundState:
    available: bool
    message: str = ""
    server: str = ""
    outputs: list = field(default_factory=list)
    inputs: list = field(default_factory=list)
    default_output: str = ""
    default_input: str = ""
    def output(self): return next((d for d in self.outputs if d.name==self.default_output),self.outputs[0] if self.outputs else None)
    def input(self): return next((d for d in self.inputs if d.name==self.default_input),self.inputs[0] if self.inputs else None)

_HEADER=re.compile(r"^(Sink|Source) #(\d+)\s*$")
_PERCENT=re.compile(r"(\d+)%")

def parse_devices(text, kind):
    """`pactl list sinks` or `pactl list sources` (C locale) -> [Device]."""
    devices=[]; cur=None; section=""
    for line in text.splitlines():
        m=_HEADER.match(line)
        if m:
            cur=Device(kind,int(m.group(2)),"","",0,False); devices.append(cur); section=""; continue
        if cur is None or not line.strip(): continue
        depth=len(line)-len(line.lstrip("\t"))
        stripped=line.strip()
        if depth==1:
            key,_,value=stripped.partition(":"); value=value.strip(); section=key
            if key=="Name": cur.name=value
            elif key=="Description": cur.description=value
            elif key=="Mute": cur.muted=value=="yes"
            elif key=="Volume":
                levels=[int(p) for p in _PERCENT.findall(value)]
                cur.volume=round(sum(levels)/len(levels)) if levels else 0
            elif key=="Active Port": cur.active_port=value
            elif key=="Monitor of Sink": cur.is_monitor=value not in ("","n/a")
        elif depth>=2 and section=="Properties":
            key,_,value=stripped.partition("=")
            key=key.strip(); value=value.strip().strip('"')
            if key=="device.class" and value=="monitor": cur.is_monitor=True
            elif key=="device.icon_name": cur.icon=value
        elif depth==2 and section=="Ports":
            name,found,rest=stripped.partition(": ")
            if found:   # "analog-output-speaker: Speakers (type: Speaker, priority: 10000, availability unknown)"
                label,_,details=rest.rpartition(" (") if rest.endswith(")") else (rest,"","")
                cur.ports.append(Port(name,label or rest,"not available" not in details))
    return devices

def parse_info(text):
    """`pactl info` -> (default sink, default source, server name)."""
    info=key_values(text)
    return info.get("Default Sink",""),info.get("Default Source",""),info.get("Server Name","")

def server_label(server):
    """'PulseAudio (on PipeWire 1.0.5)' -> 'PipeWire 1.0.5'; 'pulseaudio' -> 'PulseAudio'."""
    m=re.search(r"on (PipeWire[^)]*)\)",server)
    if m: return m.group(1).strip()
    return "PulseAudio" if server.lower().startswith("pulseaudio") else server

def read_state():
    if not have("pactl"):
        return SoundState(False,"Sound settings need pactl, from PulseAudio or PipeWire (the pulseaudio-utils, libpulse or pipewire-pulse package).")
    info=run(["pactl","info"],timeout=5)
    if not info.ok:
        return SoundState(False,f"No sound server is answering ({info.message}). Is PipeWire or PulseAudio running?")
    sinks=run(["pactl","list","sinks"],timeout=5); sources=run(["pactl","list","sources"],timeout=5)
    default_sink,default_source,server=parse_info(info.out)
    inputs=[d for d in parse_devices(sources.out,"source") if not d.is_monitor]
    return SoundState(True,"",server_label(server),parse_devices(sinks.out,"sink"),inputs,default_sink,default_source)

def stepped(volume, step):
    """The next volume a − / + press lands on: a multiple of VOLUME_STEP, within 0..MAX_VOLUME."""
    target=(volume//VOLUME_STEP+1)*VOLUME_STEP if step>0 else max(0,volume-1)//VOLUME_STEP*VOLUME_STEP
    return max(0,min(MAX_VOLUME,target))

def set_volume(device, percent):
    return run(["pactl",f"set-{device.kind}-volume",device.name,f"{max(0,min(MAX_VOLUME,int(percent)))}%"],timeout=5)

def set_muted(device, muted):
    return run(["pactl",f"set-{device.kind}-mute",device.name,"1" if muted else "0"],timeout=5)

def set_port(device, port):
    return run(["pactl",f"set-{device.kind}-port",device.name,port],timeout=5)

def parse_short_streams(text):
    """`pactl list short sink-inputs` -> [stream index]."""
    return [int(line.split()[0]) for line in text.splitlines() if line.split() and line.split()[0].isdigit()]

def make_default(device):
    """Use this device from now on. Sound already playing moves too (PipeWire does that by itself; PulseAudio does not)."""
    result=run(["pactl",f"set-default-{device.kind}",device.name],timeout=5)
    if result.ok:
        streams=run(["pactl","list","short","sink-inputs" if device.kind=="sink" else "source-outputs"],timeout=5)
        for index in parse_short_streams(streams.out):
            run(["pactl","move-sink-input" if device.kind=="sink" else "move-source-output",str(index),device.name],timeout=5)
    return result
