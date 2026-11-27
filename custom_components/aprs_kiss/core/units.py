"""Units the user sees: kilometres or miles, °C or °F, hPa or inHg (inches of mercury, the US).

Everything inside the app stays metric (km, m, km/h, °C, m/s); only what is shown and typed in is
converted. The default follows the country the phone or computer is set to (miles in the US, the UK,
Liberia and Myanmar; Fahrenheit in the US and a few places that follow it); Settings can choose either.
"""

from __future__ import annotations

from dataclasses import dataclass

KM_PER_MI = 1.609344
FT_PER_M = 3.280839895

MILES_COUNTRIES = {"US", "GB", "LR", "MM"}
FAHRENHEIT_COUNTRIES = {"US", "LR", "BS", "BZ", "KY", "PW", "FM", "MH"}
INHG_COUNTRIES = {"US"}  # the UK and Australia: hPa (millibars), as in Europe
HPA_PER_INHG = 33.8638866667

# the choices of "how far" in the map filter: the same steps in either unit, kept in whole kilometres
REACH_KM = (20, 50, 100)
REACH_MI = (10, 30, 60)


def system_distance(country: str | None) -> str:
    return "mi" if (country or "").upper() in MILES_COUNTRIES else "km"


def system_temperature(country: str | None) -> str:
    return "F" if (country or "").upper() in FAHRENHEIT_COUNTRIES else "C"


def system_pressure(country: str | None) -> str:
    return "inHg" if (country or "").upper() in INHG_COUNTRIES else "hPa"


@dataclass(frozen=True)
class Units:
    distance: str = "km"  # "km" or "mi"
    temperature: str = "C"  # "C" or "F"
    comma: bool = False  # a decimal comma (most of the app's languages)
    pressure: str = "hPa"  # "hPa" or "inHg"

    @classmethod
    def choose(cls, distance: str, temperature: str, country: str | None, comma: bool = False,
               pressure: str = "") -> Units:
        """distance / temperature / pressure as saved in the settings ("" = as the system says)."""
        return cls(distance if distance in ("km", "mi") else system_distance(country),
                   temperature if temperature in ("C", "F") else system_temperature(country), comma,
                   pressure if pressure in ("hPa", "inHg") else system_pressure(country))

    @property
    def miles(self) -> bool:
        return self.distance == "mi"

    @property
    def unit(self) -> str:
        """The unit of distances: "km" or "mi"."""
        return self.distance

    def _num(self, value: float, digits: int) -> str:
        text = f"{value:.{digits}f}"
        return text.replace(".", ",") if self.comma else text

    # ─── distances ─────

    def from_km(self, km: float) -> float:
        """A distance in the user's unit (km or mi)."""
        return km / KM_PER_MI if self.miles else km

    def to_km(self, value: float) -> float:
        """A distance typed in the user's unit, in km."""
        return value * KM_PER_MI if self.miles else value

    def distance_text(self, km: float) -> str:
        """"350 m", "4.25 km", "12.5 km", "120 km"; or "900 ft", "2.64 mi", "12.5 mi", "75 mi"."""
        if self.miles:
            mi = km / KM_PER_MI
            if mi < 0.2:
                return f"{round(km * 1000 * FT_PER_M, -1):.0f} ft"
            value, unit = mi, "mi"
        else:
            if km < 1:
                return f"{km * 1000:.0f} m"
            value, unit = km, "km"
        digits = 2 if value < 10 else 1 if value < 100 else 0
        return f"{self._num(value, digits)} {unit}"

    def distance_short(self, km: float) -> str:
        """A distance for a list: "350 m", "3.4 km", "12 km" (or ft / mi)."""
        if self.miles:
            mi = km / KM_PER_MI
            if mi < 0.2:
                return f"{round(km * 1000 * FT_PER_M, -1):.0f} ft"
            return f"{self._num(mi, 1)} mi" if mi < 10 else f"{mi:.0f} mi"
        if km < 1:
            return f"{km * 1000:.0f} m"
        return f"{self._num(km, 1)} km" if km < 10 else f"{km:.0f} km"

    def choice(self, km: float) -> str:
        """A distance offered in a list of choices: "5 km" as it is; in miles "3.1 mi"."""
        return self.distance_short(km) if self.miles else f"{km:g} km"

    def whole(self, km: float) -> str:
        """A whole number of the user's unit: "20 km", "12 mi"."""
        return f"{self.from_km(km):.0f} {self.unit}"

    def length(self, metres: float) -> str:
        """A short length (altitude, accuracy): "350 m" or "1150 ft"."""
        return f"{metres * FT_PER_M:.0f} ft" if self.miles else f"{metres:.0f} m"

    def speed(self, kmh: float) -> str:
        return f"{kmh / KM_PER_MI:.0f} mph" if self.miles else f"{kmh:.0f} km/h"

    def wind(self, ms: float) -> str:
        """Wind (m/s inside): mph with miles, else m/s."""
        return f"{ms * 3.6 / KM_PER_MI:.0f} mph" if self.miles else f"{self._num(ms, 1)} m/s"

    # ─── temperature ─────

    def temperature_value(self, celsius: float) -> float:
        return celsius * 9 / 5 + 32 if self.temperature == "F" else celsius

    @property
    def degree(self) -> str:
        return "°F" if self.temperature == "F" else "°C"

    def temperature_text(self, celsius: float) -> str:
        return f"{self._num(self.temperature_value(celsius), 1)} {self.degree}"

    # ─── pressure (hPa inside) ─────

    def pressure_text(self, hpa: float) -> str:
        """"1013 hPa" or "29.92 inHg"."""
        if self.pressure == "inHg":
            return f"{self._num(hpa / HPA_PER_INHG, 2)} inHg"
        return f"{hpa:.0f} hPa"

    # ─── the "how far" choices ─────

    def reach_choices(self) -> tuple[tuple[int, str], ...]:
        """((km, label), …) for the map filter: 20 / 50 / 100 km, or 10 / 30 / 60 mi (kept as km)."""
        if self.miles:
            return tuple((round(mi * KM_PER_MI), str(mi)) for mi in REACH_MI)
        return tuple((km, str(km)) for km in REACH_KM)


current = Units()  # what the app shows now (set by the app from the settings and the system)
