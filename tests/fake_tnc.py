#!/usr/bin/env python3
"""A simulated KISS TNC on TCP, for trying the integration without a radio.

It plays the radio channel:
- every --interval seconds it "receives" an APRS packet (positions, a status,
  a message to our callsign) and sends it to the client;
- it answers APRS messages addressed to it with an ack;
- it is a small BBS (OK0BBS by default) that accepts AX.25 connections and
  answers commands (H for help, L to list, B to say bye).

Run: python3 tests/fake_tnc.py --port 8001 --mycall OK1SIM-7
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "aprs_kiss"


def _load(name):
    pkg = sys.modules.setdefault("aprs_kiss", types.ModuleType("aprs_kiss"))
    pkg.__path__ = [str(ROOT)]
    spec = importlib.util.spec_from_file_location(f"aprs_kiss.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


ax25 = _load("ax25")
aprs = _load("aprs")
session = _load("session")

A = ax25.Address.parse

SAMPLES = [
    ("OK1ABC-9", "APRS", ["OK0DIG*", "WIDE2-1"], "=4945.12N/01322.50E>Mobile on the D5 motorway"),
    ("OK1XYZ", "APRS", ["WIDE1-1"], "!4935.00N/01245.00E-QTH Stod area"),
    ("OK2DEF-7", "APRS", ["OK0DIG*"], ">Listening on 144.800"),
    ("OK1WX", "APRS", [], "@161200z4936.50N/01310.00E_090/005g010t050r000p000P000h80b10150Weather"),
]


class FakeTnc:
    def __init__(self, args):
        self.args = args
        self.writer = None
        self.bbs_call = A(args.bbs)
        self.sessions: dict[str, object] = {}
        self.msg_no = 0

    async def send_to_client(self, frame: ax25.Frame) -> None:
        if self.writer is not None:
            self.writer.write(ax25.kiss_frame(frame.encode()))
            await self.writer.drain()

    async def beacons(self):
        i = 0
        while True:
            await asyncio.sleep(self.args.interval)
            src, dst, path, info = SAMPLES[i % len(SAMPLES)]
            i += 1
            await self.send_to_client(ax25.Frame(A(dst), A(src), [A(p) for p in path], info.encode()))
            if i % 3 == 0:
                self.msg_no += 1
                text = f":{aprs.addressee(self.args.mycall)}:Test message {self.msg_no} from the simulator{{{self.msg_no}"
                await self.send_to_client(ax25.Frame(A("APRS"), A("OK1ABC-9"), [A("WIDE1-1")], text.encode()))

    def bbs_session(self, remote: ax25.Address):
        key = str(remote)
        if key in self.sessions:
            return self.sessions[key]

        async def send(raw: bytes):
            await self.send_to_client(ax25.Frame.decode(raw))

        def on_text(text: str):
            for line in text.splitlines():
                cmd = line.strip().upper()
                if cmd.startswith("H"):
                    reply = "Commands: H help, L list messages, B bye\r"
                elif cmd.startswith("L"):
                    reply = "".join(f"{n:4d}  OK1XYZ  Test bulletin {n}\r" for n in range(1, 21))
                elif cmd.startswith("B"):
                    sess.send_text("73, bye\r")
                    asyncio.get_event_loop().call_later(2, sess.disconnect)
                    continue
                else:
                    reply = f"Unknown command: {line.strip()}\r"
                sess.send_text(reply + f"{self.bbs_call}> ")

        def on_state(state: str, reason: str):
            print(f"BBS session {key}: {state} ({reason})", flush=True)
            if state == "connected":
                sess.send_text(f"Welcome to {self.bbs_call}, the simulated BBS.\rType H for help.\r{self.bbs_call}> ")

        sess = session.Session(self.bbs_call, remote, [], send, on_text, on_state)
        self.sessions[key] = sess
        return sess

    async def handle_from_client(self, frame: ax25.Frame):
        print(f"<< {frame.monitor()}", flush=True)
        if frame.is_ui and frame.info.startswith(b":"):
            body = frame.info.decode("latin-1")
            addressee, _, text = body[1:].partition(":")
            if addressee.strip() == "OK1ABC-9" and "{" in text and not text.startswith("ack"):
                no = text.rsplit("{", 1)[1]
                await asyncio.sleep(2)
                ack = f":{aprs.addressee(str(frame.source))}:ack{no}"
                await self.send_to_client(ax25.Frame(A("APRS"), A("OK1ABC-9"), [], ack.encode()))
            return
        if frame.destination == self.bbs_call and not frame.is_ui:
            self.bbs_session(frame.source).handle(frame)

    async def client(self, reader, writer):
        print("client connected", flush=True)
        self.writer = writer
        decoder = ax25.KissDecoder()
        try:
            while data := await reader.read(1024):
                for raw in decoder.feed(data):
                    await self.handle_from_client(ax25.Frame.decode(raw))
        finally:
            self.writer = None
            print("client disconnected", flush=True)

    async def run(self):
        server = await asyncio.start_server(self.client, "0.0.0.0", self.args.port)
        print(f"fake KISS TNC on :{self.args.port}, BBS {self.bbs_call}", flush=True)
        async with server:
            await asyncio.gather(server.serve_forever(), self.beacons())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--mycall", default="OK1SIM-7")
    p.add_argument("--bbs", default="OK0BBS")
    p.add_argument("--interval", type=float, default=20)
    asyncio.run(FakeTnc(p.parse_args()).run())
