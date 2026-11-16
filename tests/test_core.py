"""Tests of the parts without Home Assistant: KISS, AX.25, APRS building, AX.25 sessions.

Run: python3 -m unittest discover -s tests -t .
"""

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1] / "custom_components" / "aprs_kiss"


def _load(name):
    """Import a module of the integration without running its __init__ (which needs HA)."""
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
station = _load("station")


class KissTest(unittest.TestCase):
    def test_round_trip_with_escapes(self):
        payload = bytes([1, ax25.FEND, 2, ax25.FESC, 3])
        decoder = ax25.KissDecoder()
        frames = decoder.feed(ax25.kiss_frame(payload)[:4]) + decoder.feed(ax25.kiss_frame(payload)[4:])
        self.assertEqual(frames, [payload])

    def test_parameter_frames_are_ignored(self):
        decoder = ax25.KissDecoder()
        self.assertEqual(decoder.feed(ax25.kiss_frame(b"\x1e", ax25.CMD_TXDELAY)), [])


class Ax25Test(unittest.TestCase):
    def test_ui_round_trip(self):
        f = ax25.Frame(ax25.Address.parse("APZHAK"), ax25.Address.parse("OK1SIM-7"),
                       [ax25.Address.parse("WIDE1-1"), ax25.Address.parse("WIDE2-1")], b">hello")
        g = ax25.Frame.decode(f.encode())
        self.assertEqual(g.tnc2(), "OK1SIM-7>APZHAK,WIDE1-1,WIDE2-1:>hello")
        self.assertTrue(g.is_ui)
        self.assertTrue(g.command)

    def test_digipeated_flag(self):
        f = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OK1ABC"),
                       [ax25.Address.parse("OK0XYZ*"), ax25.Address.parse("WIDE2-1")], b"!x")
        self.assertIn("OK0XYZ*,WIDE2-1", ax25.Frame.decode(f.encode()).tnc2())

    def test_i_frame_fields_and_monitor(self):
        f = ax25.Frame(ax25.Address.parse("OK0BBS"), ax25.Address.parse("OK1SIM-7"), [], b"hi\r",
                       control=(3 << 5) | (2 << 1), command=True)
        g = ax25.Frame.decode(f.encode())
        self.assertEqual((g.kind, g.ns, g.nr), ("I", 2, 3))
        self.assertEqual(g.monitor(), "OK1SIM-7>OK0BBS <I C S2 R3>: hi\n")

    def test_bad_callsign(self):
        with self.assertRaises(ValueError):
            ax25.Address.parse("TOOLONGCALL")
        with self.assertRaises(ValueError):
            ax25.Address.parse("OK1SIM-16")


class AprsBuildTest(unittest.TestCase):
    def test_message_and_ack(self):
        self.assertEqual(aprs.message("ok1abc", "Hi|there", "12"), ":OK1ABC   :Hithere{12")
        self.assertEqual(aprs.ack("OK1ABC-9", "12"), ":OK1ABC-9 :ack12")

    def test_position(self):
        self.assertEqual(aprs.position(49.6160827, 13.1628307, "/-", "QTH"), "=4936.96N/01309.77E-QTH")
        self.assertEqual(aprs.position(-33.5, -70.25, "/>"), "=3330.00S/07015.00W>")

    def test_status_is_cut(self):
        self.assertEqual(len(aprs.status("x" * 100)), 1 + aprs.MAX_STATUS_TEXT)


class Link:
    """Two sessions joined by a fake radio that can lose chosen frames."""

    def __init__(self):
        self.a = self.b = None
        self.drop = set()  # indexes of frames (counted from 0) to lose
        self.count = 0
        self.log = []

    def sender(self, to_attr):
        async def send(raw):
            frame = ax25.Frame.decode(raw)
            idx = self.count
            self.count += 1
            self.log.append(("drop " if idx in self.drop else "") + frame.monitor())
            if idx in self.drop:
                return
            asyncio.get_event_loop().call_soon(getattr(self, to_attr).handle, frame)
        return send


class SessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        session.T1 = 0.3
        session.T2 = 0.05
        self.link = Link()
        self.got_a, self.got_b, self.states_a, self.states_b = [], [], [], []
        me, bbs = ax25.Address.parse("OK1SIM-7"), ax25.Address.parse("OK0BBS")
        self.link.a = session.Session(me, bbs, [], self.link.sender("b"), self.got_a.append,
                                      lambda s, r: self.states_a.append(s))
        self.link.b = session.Session(bbs, me, [], self.link.sender("a"), self.got_b.append,
                                      lambda s, r: self.states_b.append(s))

    async def asyncTearDown(self):
        self.link.a.close()
        self.link.b.close()

    async def _settle(self, seconds=0.2):
        await asyncio.sleep(seconds)

    async def test_connect_talk_disconnect(self):
        self.link.a.connect()
        await self._settle()
        self.assertEqual(self.link.a.state, session.CONNECTED)
        self.assertEqual(self.link.b.state, session.CONNECTED)
        self.link.a.send_text("help\n")
        self.link.b.send_text("Welcome to the BBS\n")
        await self._settle(0.3)
        self.assertEqual("".join(self.got_b), "help\n")
        self.assertEqual("".join(self.got_a), "Welcome to the BBS\n")
        self.link.a.disconnect()
        await self._settle()
        self.assertEqual(self.link.a.state, session.DISCONNECTED)
        self.assertEqual(self.link.b.state, session.DISCONNECTED)

    async def test_long_text_uses_the_window_and_arrives_whole(self):
        self.link.a.connect()
        await self._settle()
        text = "".join(f"line {i:03d} of a long listing\n" for i in range(60))
        self.link.b.send_text(text)
        await self._settle(2.0)
        self.assertEqual("".join(self.got_a), text)

    async def test_lost_i_frame_is_sent_again(self):
        self.link.a.connect()
        await self._settle()
        self.link.drop = {self.link.count}  # the next frame (the first I frame) is lost
        self.link.a.send_text("first\n")
        self.link.a.send_text("second\n")
        await self._settle(1.5)
        self.assertEqual("".join(self.got_b), "first\nsecond\n")

    async def test_refused_connection(self):
        self.link.b.handle = lambda f: asyncio.get_event_loop().call_soon(
            self.link.a.handle, ax25.Frame(f.source, f.destination, [], b"", ax25.U_DM | ax25.PF, None, False))
        self.link.a.connect()
        await self._settle()
        self.assertEqual(self.link.a.state, session.DISCONNECTED)

    async def test_no_answer_gives_up(self):
        session.N2 = 2
        self.link.drop = set(range(1000))
        self.link.a.connect()
        await self._settle(1.5)
        self.assertEqual(self.link.a.state, session.DISCONNECTED)
        session.N2 = 8


class StationTest(unittest.IsolatedAsyncioTestCase):
    async def test_message_to_me_is_acked_once_and_reported_once(self):
        sent, messages = [], []

        async def send(raw):
            sent.append(ax25.Frame.decode(raw).tnc2())

        def parse(tnc2):
            src, _, rest = tnc2.partition(">")
            body = rest.split(":", 1)[1]
            addressee, text = body[1:10], body[11:]
            text, _, no = text.partition("{")
            return {"from": src, "format": "message", "addresse": addressee.strip(), "message_text": text, "msgNo": no}

        st = station.Station(station.StationConfig("OK1SIM-7"), send, parse, lambda p: None,
                             messages.append, lambda: None, lambda: 1)
        st.tx_enabled = True
        msg = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OK1ABC"), [], b":OK1SIM-7 :hello{7").encode()
        st.handle_frame(msg)
        st.handle_frame(msg)  # digipeated copy within 30 s: duplicate
        await asyncio.sleep(0.1)
        self.assertEqual([m["text"] for m in messages], ["hello"])
        self.assertEqual(sent, ["OK1SIM-7>APZHAK,WIDE1-1,WIDE2-1::OK1ABC   :ack7"])
        await st.close()

    async def test_internet_station_is_marked_until_the_radio_hears_it(self):
        async def send(raw):
            pass

        def parse(tnc2):
            return {"from": tnc2.partition(">")[0], "format": "uncompressed", "latitude": 49.7, "longitude": 13.3}

        st = station.Station(station.StationConfig("OK1SIM-7"), send, parse, lambda p: None,
                             lambda m: None, lambda: None, lambda: 1)
        st.handle_is_packet({"from": "OK1XYZ", "format": "uncompressed", "latitude": 49.7, "longitude": 13.3,
                             "raw": "OK1XYZ>APRS,TCPIP*,qAC,T2:!...", "path": ["TCPIP*", "qAC", "T2"]})
        self.assertIn("last_is", st.heard["OK1XYZ"])
        self.assertNotIn("last_rf", st.heard["OK1XYZ"])
        st.handle_frame(ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OK1XYZ"),
                                   [ax25.Address.parse("WIDE1-1")], b"!4942.00N/01318.00E-").encode())
        self.assertIn("last_rf", st.heard["OK1XYZ"])
        self.assertEqual(st.heard["OK1XYZ"]["path"], ["WIDE1-1"])
        # A later internet copy keeps the radio path.
        st.handle_is_packet({"from": "OK1XYZ", "format": "uncompressed", "raw": "x", "path": ["TCPIP*"]})
        self.assertEqual(st.heard["OK1XYZ"]["path"], ["WIDE1-1"])
        await st.close()

    async def test_transmit_switched_off(self):
        async def send(raw):
            raise AssertionError("must not send")

        st = station.Station(station.StationConfig("OK1SIM-7"), send, lambda t: {}, lambda p: None,
                             lambda m: None, lambda: None, lambda: 1)
        with self.assertRaises(station.TransmitRefused):
            await st.send_status("test")


if __name__ == "__main__":
    unittest.main()


class WeatherTest(unittest.TestCase):
    def test_wind_from_course_and_speed(self):
        st = station.Station(station.StationConfig("OK1SIM-7"), None, lambda t: {
            "from": "OK1WX", "format": "uncompressed", "latitude": 49.6, "longitude": 13.1,
            "course": 90, "speed": 5 * 1.852, "weather": {"temperature": 10.0, "humidity": 80}},
            lambda p: None, lambda m: None, lambda: None, lambda: 1)
        raw = ax25.Frame(ax25.Address.parse("APRS"), ax25.Address.parse("OK1WX"), [], b"@x").encode()
        st.handle_frame(raw)
        wx = st.heard["OK1WX"]["weather"]
        self.assertEqual(wx["wind_direction"], 90)
        self.assertAlmostEqual(wx["wind_speed"], 2.24, places=2)  # 5 mph
        self.assertNotIn("speed", st.heard["OK1WX"])


aprsis = _load("aprsis")


class AprsIsTest(unittest.TestCase):
    def test_licence_statement(self):
        ok = aprsis.licence_confirmed
        self.assertTrue(ok("mám platnou radioamatérskou licenci"))
        self.assertTrue(ok("  Mam platnou  radioamaterskou licenci. "))
        self.assertTrue(ok("I hold a valid amateur radio license"))
        self.assertFalse(ok("mám licenci"))
        self.assertFalse(ok(""))
        self.assertFalse(ok(None))

    def test_passcode(self):
        self.assertEqual(aprsis.passcode("N0CALL"), 13023)
        self.assertEqual(aprsis.passcode("n0call-9"), 13023)  # SSID and case do not matter

    def test_gate_to_is(self):
        line = aprsis.gate_to_is("OK1ABC-9", "APRS", ["OK0DIG*", "WIDE2-1"], b"=4945.12N/01322.50E>hi", "OK1SIM-7")
        self.assertEqual(line, "OK1ABC-9>APRS,OK0DIG*,WIDE2-1,qAR,OK1SIM-7:=4945.12N/01322.50E>hi")

    def test_not_gated(self):
        for path, info in ((["NOGATE"], b"!x"), (["RFONLY"], b"!x"), (["TCPIP*"], b"!x"), ([], b"?APRS?"),
                           ([], b"}OK1A>APRS,TCPIP,OK1B*::OK1C     :hi")):
            self.assertIsNone(aprsis.gate_to_is("OK1ABC", "APRS", path, info, "OK1SIM-7"), (path, info))

    def test_third_party(self):
        self.assertEqual(aprsis.third_party("OK1ABC", "APRS", ":OK1DEF   :hi{1", "OK1SIM-7"),
                         "}OK1ABC>APRS,TCPIP,OK1SIM-7*::OK1DEF   :hi{1")
