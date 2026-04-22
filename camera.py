#!/usr/bin/env python3
"""
camera.py — Jetson USB Camera Live Feed (Display Mode)
NET-SCAN // ARASAKA ANOMALY DETECTION SYSTEM
Lightweight live window — full cyberpunk HUD only on scan results
"""

import sys
import cv2
import time
import argparse
import threading
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich.align import Align
from rich import box

from detector import (
    run_detection, render_output,
    BGR_YELLOW, BGR_RED, BGR_DIM, BGR_ORANGE,
    SEVERITY_BGR,
)

console = Console()
Y  = "bold yellow"
DM = "dim yellow"
RD = "bold red"

BANNER = r"""
 ███╗   ██╗███████╗████████╗      ███████╗ ██████╗ █████╗ ███╗   ██╗
 ████╗  ██║██╔════╝╚══██╔══╝      ██╔════╝██╔════╝██╔══██╗████╗  ██║
 ██╔██╗ ██║█████╗     ██║   █████╗███████╗██║     ███████║██╔██╗ ██║
 ██║╚██╗██║██╔══╝     ██║   ╚════╝╚════██║██║     ██╔══██║██║╚██╗██║
 ██║ ╚████║███████╗   ██║         ███████║╚██████╗██║  ██║██║ ╚████║
 ╚═╝  ╚═══╝╚══════╝   ╚═╝         ╚══════╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝
  ARASAKA CORP // NET-SCAN // YOLOv8 // 100% OPEN SOURCE
"""

SEVERITY_STYLE = {
    "low":      "yellow",
    "medium":   "color(202)",
    "high":     "bold red",
    "critical": "bold white on red",
}

def print_banner():
    console.print(Text(BANNER, style="bold yellow"))

def print_results(result, elapsed, output_path):
    objects   = result.get("objects", [])
    anomalies = [o for o in objects if o.get("is_anomaly")]
    normals   = [o for o in objects if not o.get("is_anomaly")]
    threat    = result.get("overall_threat", 0)
    avg_conf  = round(sum(o.get("confidence", 0) for o in objects) / max(len(objects), 1))
    t_style   = RD if threat >= 70 else "bold color(202)" if threat >= 40 else Y

    console.print()
    console.print(Rule(Text("▓▓  SCAN COMPLETE — NET-SCAN REPORT  ▓▓", style=Y), style="yellow"))
    stats = Table(box=None, padding=(0, 4), show_header=False)
    for _ in range(5): stats.add_column(justify="center")
    stats.add_row(
        f"[bold yellow]{len(objects)}[/]\n[dim]TARGETS[/]",
        f"[bold {'red' if anomalies else 'green'}]{len(anomalies)}[/]\n[dim]THREATS[/]",
        f"[{t_style}]{threat}%[/]\n[dim]THREAT INDEX[/]",
        f"[bold green]{avg_conf}%[/]\n[dim]AVG CONF[/]",
        f"[bold yellow]{elapsed:.2f}s[/]\n[dim]PROC TIME[/]",
    )
    console.print(Align.center(stats))
    console.print()
    if anomalies:
        console.print(Panel(f"[bold red]▓ {len(anomalies)} THREAT(S) IDENTIFIED ▓[/]", border_style="red"))
        t = Table(box=box.SIMPLE_HEAVY, border_style="yellow", header_style="bold yellow", show_lines=True, padding=(0,1))
        t.add_column("ID",    style=DM,          width=7)
        t.add_column("TARGET",style="bold white", min_width=14)
        t.add_column("SEV",   justify="center",   width=12)
        t.add_column("CONF",  justify="right",    width=6)
        t.add_column("THREAT VECTOR", min_width=30)
        for obj in anomalies:
            sev = obj.get("severity","low")
            t.add_row(obj.get("id","—"), obj["name"].upper(),
                      f"[{SEVERITY_STYLE.get(sev,RD)}]◈ {sev.upper()} ◈[/]",
                      f"[bold]{obj.get('confidence',0)}%[/]",
                      f"[italic dim]{obj.get('anomaly_reason','')}[/]")
        console.print(t)
    else:
        console.print(Panel("[bold green]◈ NO THREATS — SECTOR NOMINAL — ARASAKA APPROVES ◈[/]", border_style="green"))
    if normals:
        console.print()
        nt = Table(title=Text("◈ IDENTIFIED — NON-HOSTILE", style=Y), box=box.MINIMAL, border_style=DM, header_style=DM, padding=(0,1))
        nt.add_column("TARGET", style="yellow", min_width=14)
        nt.add_column("CONF",   justify="right", width=6)
        for obj in normals:
            nt.add_row(obj["name"].upper(), f"{obj.get('confidence',0)}%")
        console.print(nt)
    console.print()
    console.print(f"[bold yellow]▓ OUTPUT SAVED:[/] [underline]{output_path}[/]")


def list_cameras(max_index=6):
    found = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            found.append(i)
            cap.release()
    return found


def open_camera(index, width=640, height=480):
    cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open /dev/video{index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    for _ in range(6):
        cap.read()
        time.sleep(0.03)
    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    console.print(f"[yellow]▓ CAMERA  :[/]  /dev/video{index}  →  {aw}×{ah}")
    return cap


def draw_live_overlay(frame, scanning, scan_count, interval, last_scan_t, last_result):
    """Fast minimal overlay drawn every frame — no heavy effects."""
    h, w = frame.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    arc  = BGR_YELLOW
    red  = BGR_RED
    dim  = BGR_DIM

    # Border + corners
    cv2.rectangle(frame, (0,0), (w-1,h-1), arc, 1)
    bl = 30
    for cx,cy,dx,dy in [(0,0,1,1),(w-1,0,-1,1),(0,h-1,1,-1),(w-1,h-1,-1,-1)]:
        cv2.line(frame,(cx,cy),(cx+dx*bl,cy),arc,2)
        cv2.line(frame,(cx,cy),(cx,cy+dy*bl),arc,2)

    # Top-left status
    ts     = datetime.now().strftime("%H:%M:%S")
    status = "SCANNING..." if scanning else "STANDBY"
    col    = red if scanning else arc
    cv2.rectangle(frame,(0,0),(260,62),(8,5,14),-1)
    cv2.putText(frame,f"NET-SCAN  {status}",(8,18),font,0.45,col,2,cv2.LINE_AA)
    cv2.putText(frame,f"{ts}  SCANS:{scan_count}",(8,38),font,0.38,dim,1,cv2.LINE_AA)
    if interval > 0 and not scanning:
        remaining = max(0, interval - int(time.time() - last_scan_t))
        cv2.putText(frame,f"NEXT SCAN: {remaining}s",(8,56),font,0.35,dim,1,cv2.LINE_AA)

    # Top-right threat
    if last_result:
        threat = last_result.get("overall_threat", 0)
        tc     = red if threat >= 70 else BGR_ORANGE if threat >= 40 else arc
        anoms  = sum(1 for o in last_result.get("objects",[]) if o.get("is_anomaly"))
        cv2.rectangle(frame,(w-185,0),(w,50),(8,5,14),-1)
        cv2.putText(frame,f"THREAT: {threat}%",(w-178,18),font,0.45,tc,2,cv2.LINE_AA)
        cv2.putText(frame,f"ANOMALIES: {anoms}",(w-178,38),font,0.38,tc,1,cv2.LINE_AA)

    # Bottom help
    cv2.rectangle(frame,(0,h-22),(w,h),(8,5,14),-1)
    cv2.putText(frame,"SPACE:scan  S:save  Q:quit",(8,h-7),font,0.38,dim,1,cv2.LINE_AA)

    # Light bboxes from last scan
    if last_result:
        for obj in last_result.get("objects",[]):
            b = obj.get("bbox_pct",{})
            if not b: continue
            x1=int(b["x"]/100*w); y1=int(b["y"]/100*h)
            x2=x1+int(b["w"]/100*w); y2=y1+int(b["h"]/100*h)
            x1,y1=max(0,x1),max(0,y1); x2,y2=min(w-1,x2),min(h-1,y2)
            is_a  = obj.get("is_anomaly",False)
            color = SEVERITY_BGR.get(obj["severity"],red) if is_a else arc
            cv2.rectangle(frame,(x1,y1),(x2,y2),color,2)
            lbl = f"{'[!]' if is_a else '[+]'} {obj['name'].upper()} {obj['confidence']}%"
            cv2.putText(frame,lbl,(x1+2,max(y1-4,10)),font,0.38,color,1,cv2.LINE_AA)
    return frame


class LivePreview:
    def __init__(self, cap, output_dir, weights, interval):
        self.cap        = cap
        self.output_dir = Path(output_dir)
        self.weights    = weights
        self.interval   = interval
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._last_result     = None
        self._last_ann        = None
        self._scanning        = False
        self._lock            = threading.Lock()
        self._last_scan_t     = 0.0
        self._scan_count      = 0
        self._show_result     = False
        self._result_shown_at = 0.0

    def _do_scan(self, frame):
        with self._lock:
            if self._scanning: return
            self._scanning = True
        try:
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = str(self.output_dir / f"raw_{ts}.jpg")
            ann_path = str(self.output_dir / f"scan_{ts}_netscan.jpg")
            cv2.imwrite(raw_path, frame)
            console.print(f"\n[yellow]▓ SCANNING…[/]  [{ts}]")
            t0      = time.time()
            result  = run_detection(raw_path, weights=self.weights)
            render_output(raw_path, result, ann_path)
            elapsed = time.time() - t0
            ann = cv2.imread(ann_path)
            if ann is not None: self._last_ann = ann
            self._last_result     = result
            self._scan_count     += 1
            self._last_scan_t     = time.time()
            self._show_result     = True
            self._result_shown_at = time.time()
            print_results(result, elapsed, ann_path)
            Path(raw_path).unlink(missing_ok=True)
        except Exception as ex:
            console.print(f"[bold red]▓ SCAN ERROR:[/] {ex}")
        finally:
            self._scanning = False

    def _trigger_scan(self, frame):
        threading.Thread(target=self._do_scan, args=(frame.copy(),), daemon=True).start()

    def run(self):
        console.print(Panel(
            Text(
                "LIVE CAMERA FEED ACTIVE\n"
                "  SPACE → manual scan   S → save frame   Q/ESC → quit\n"
                f"  Auto-scan: {'OFF' if self.interval==0 else f'every {self.interval}s'}",
                justify="center", style=Y,
            ), border_style="yellow", padding=(0,3)))

        win = "NET-SCAN // ARASAKA CORP"
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 800, 600)

        try:
            while True:
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.05)
                    continue

                if (self.interval > 0 and not self._scanning
                        and time.time() - self._last_scan_t >= self.interval):
                    self._trigger_scan(frame)

                # Show full annotated result for 5s after scan, then back to live feed
                if (self._show_result and self._last_ann is not None
                        and time.time() - self._result_shown_at < 5.0):
                    fh, fw = frame.shape[:2]
                    display = cv2.resize(self._last_ann, (fw, fh))
                else:
                    self._show_result = False
                    display = frame.copy()
                    display = draw_live_overlay(
                        display, self._scanning, self._scan_count,
                        self.interval, self._last_scan_t, self._last_result)

                cv2.imshow(win, display)
                key = cv2.waitKey(1) & 0xFF
                if key in (ord('q'), 27):
                    break
                elif key == ord(' '):
                    if not self._scanning: self._trigger_scan(frame)
                    else: console.print(f"[{DM}]  Scan in progress…[/]")
                elif key == ord('s'):
                    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
                    out = self.output_dir / f"frame_{ts}.jpg"
                    cv2.imwrite(str(out), frame)
                    console.print(f"[yellow]▓ FRAME SAVED:[/] {out}")
        finally:
            cv2.destroyAllWindows()
            self.cap.release()
            console.print(f"\n[{DM}]  [SYS] Session ended.[/]")


def main():
    parser = argparse.ArgumentParser(description="NET-SCAN // Jetson USB Camera")
    parser.add_argument("mode",       nargs="?", default="live", choices=["live","capture"])
    parser.add_argument("--camera",   "-c", type=int, default=0)
    parser.add_argument("--interval", "-i", type=int, default=10)
    parser.add_argument("--output",   "-o")
    parser.add_argument("--outdir",   "-d", default="netscan_output")
    parser.add_argument("--weights",  "-w", default="yolov8n.pt")
    parser.add_argument("--width",          type=int, default=640)
    parser.add_argument("--height",         type=int, default=480)
    parser.add_argument("--headless",       action="store_true")
    parser.add_argument("--list",           action="store_true")
    parser.add_argument("--no-banner",      action="store_true")
    args = parser.parse_args()

    if not args.no_banner:
        print_banner()

    if args.list:
        console.print("\n[yellow]▓ PROBING CAMERAS…[/]")
        for i in list_cameras():
            console.print(f"  [bold yellow]/dev/video{i}[/]  ← available")
        return

    cap = open_camera(args.camera, args.width, args.height)

    if args.headless:
        out_dir = Path(args.outdir)
        out_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[yellow]▓ HEADLESS — scanning every {args.interval}s[/]")
        while True:
            ret, frame = cap.read()
            if not ret: time.sleep(0.1); continue
            ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
            raw_path = str(out_dir / f"raw_{ts}.jpg")
            ann_path = str(out_dir / f"scan_{ts}_netscan.jpg")
            cv2.imwrite(raw_path, frame)
            t0      = time.time()
            result  = run_detection(raw_path, weights=args.weights)
            render_output(raw_path, result, ann_path)
            Path(raw_path).unlink(missing_ok=True)
            print_results(result, time.time()-t0, ann_path)
            time.sleep(args.interval)
    else:
        LivePreview(cap, args.outdir, args.weights, args.interval).run()


if __name__ == "__main__":
    main()
