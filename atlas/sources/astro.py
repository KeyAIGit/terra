# Космос: где именно находится эта планета и что видно с неё в небе.
#
# Зачем это симулятору. Всё, что люди в TERRA считают устройством мира,
# они выводили из неба: год, месяц, стороны света, календарь, навигацию,
# богов. Чтобы наша ветвь реальности была НАШЕЙ, небо над головой должно
# быть настоящим — с теми же звёздами, тем же наклоном оси и той же
# прецессией, которая за 12 000 лет уводит полюс от Веги к Полярной.
#
# Слои:
#   constants  — измеренные величины мира (Земля, Солнце, Луна, Галактика,
#                Вселенная) с указанием, чьё это измерение;
#   orbital    — решение Ласкара La2004: эксцентриситет орбиты, наклон оси и
#                долгота перигелия на 51 млн лет назад с шагом 1 тыс. лет
#                (это и есть циклы Миланковича — двигатель ледниковых эпох);
#   stars      — каталог HYG v4.1: 119 тыс. звёзд с положением, собственным
#                движением, расстоянием, светимостью и спектром;
#   figures    — линии созвездий (современная западная традиция);
#   planets    — средние элементы орбит планет (Standish/JPL).
#
# Ярусы: constants/stars/planets — K (измерено), orbital — K (расчёт по
# принятому решению), figures — T (традиция, а не измерение).

from __future__ import annotations

import csv
import io
import json
import os

from atlas import schema
from atlas.sources import common
from atlas.state import DATA_DIR

NAME = "astro"
TITLE = "Astronomy: constants, Laskar orbital solution, HYG stars, constellations"
LICENSE = "mixed: CC0-1.0 (HYG), public-domain-gov (JPL/IERS), CC-BY-4.0 (IMCCE)"
HOME = "https://ssp.imcce.fr/insola/earth/online/earth/La2004/"

HYG_URL = ("https://raw.githubusercontent.com/astronexus/HYG-Database/main/"
           "hyg/CURRENT/hygdata_v41.csv")
HYG_LIC = "CC0-1.0"
HYG_SRC = "https://codeberg.org/astronexus/hyg (HYG v4.1)"

LASKAR_URL = ("https://ssp.imcce.fr/insola/earth/online/earth/La2004/"
              "INSOLN.LA2004.BTL.ASC")
LASKAR_LIC = "CC-BY-4.0"
LASKAR_SRC = "Laskar et al. 2004, A&A 428, 261 (IMCCE La2004 INSOLN.BTL)"

FIG_URL = ("https://raw.githubusercontent.com/ofrohn/d3-celestial/master/"
           "data/constellations.lines.json")
FIG_LIC = "BSD-3-Clause"
FIG_SRC = "https://github.com/ofrohn/d3-celestial (constellation lines)"


# ── 1. Постоянные мира ──────────────────────────────────────────────────────
# (id, имя, имя по-русски, значение, единица, погрешность|None, область, откуда)
_IAU = "IAU 2015 Resolution B3 (nominal values)"
_IERS = "IERS Conventions 2010 / IERS numerical standards"
_WGS = "WGS 84 (NGA.STND.0036, 2014)"
_JPL = "JPL DE440 / Park et al. 2021"
_GRAV = "GRAVITY Collaboration 2019, A&A 625, L10"
_PLANCK = "Planck 2018 results VI, A&A 641, A6"
_SOFA = "IAU SOFA / Capitaine et al. 2003 (P03 precession)"

CONSTANTS = [
    # — Земля как тело —
    ("earth.radius_equatorial", "Earth equatorial radius", "экваториальный радиус Земли",
     6378137.0, "m", 0.0, "earth", _WGS),
    ("earth.flattening", "Earth flattening", "сжатие Земли",
     1 / 298.257223563, "1", None, "earth", _WGS),
    ("earth.radius_mean", "Earth volumetric mean radius", "средний радиус Земли",
     6371000.0, "m", 1000.0, "earth", _IAU),
    ("earth.GM", "Earth geocentric gravitational constant", "GM Земли",
     3.986004418e14, "m3 s-2", 8e5, "earth", _IERS),
    ("earth.mass", "Earth mass", "масса Земли", 5.97217e24, "kg", 1.3e20, "earth", _JPL),
    ("earth.g0", "standard gravity", "нормальное ускорение свободного падения",
     9.80665, "m s-2", 0.0, "earth", "CGPM 1901 (defined)"),
    ("earth.land_area", "land area", "площадь суши", 1.489e14, "m2", 1e12, "earth",
     "CIA World Factbook / USGS"),
    ("earth.ocean_area", "ocean area", "площадь океана", 3.618e14, "m2", 1e12, "earth",
     "NOAA / Eakins & Sharman 2010"),
    ("earth.ocean_mean_depth", "mean ocean depth", "средняя глубина океана",
     3682.0, "m", 10.0, "earth", "Eakins & Sharman 2010 (ETOPO1)"),
    ("earth.atm_mass", "atmosphere mass", "масса атмосферы", 5.1480e18, "kg", 1e15,
     "earth", "Trenberth & Smith 2005, J. Climate 18"),
    ("earth.magnetic_dipole", "geomagnetic dipole moment", "магнитный момент Земли",
     7.72e22, "A m2", 1e21, "earth", "IGRF-13 (2020 epoch)"),

    # — вращение и ось —
    ("earth.day_sidereal", "sidereal day", "звёздные сутки", 86164.0905, "s", 0.001,
     "rotation", _IERS),
    ("earth.day_solar_mean", "mean solar day", "средние солнечные сутки", 86400.002,
     "s", 0.001, "rotation", _IERS),
    ("earth.lod_trend", "length-of-day secular trend", "вековое удлинение суток",
     1.78e-3, "s per century", 0.3e-3, "rotation",
     "Stephenson, Morrison & Hohenkerk 2016, Proc. R. Soc. A 472"),
    ("earth.obliquity_j2000", "obliquity of ecliptic at J2000",
     "наклон земной оси на эпоху J2000", 23.4392911, "deg", 1e-6, "rotation", _SOFA),
    ("earth.obliquity_rate", "obliquity secular rate", "вековое изменение наклона оси",
     -46.836769 / 3600.0, "deg per century", None, "rotation", _SOFA),
    ("earth.precession_period", "general precession period",
     "период прецессии равноденствий", 25772.0, "yr", 10.0, "rotation", _SOFA),
    ("earth.nutation_main_period", "principal nutation period",
     "главный период нутации", 18.6, "yr", 0.01, "rotation", _IERS),

    # — орбита Земли —
    ("orbit.semi_major_axis", "Earth orbit semi-major axis", "большая полуось орбиты Земли",
     1.00000261, "au", 1e-8, "orbit", _JPL),
    ("orbit.au", "astronomical unit", "астрономическая единица", 1.495978707e11, "m",
     0.0, "orbit", "IAU 2012 Resolution B2 (defined)"),
    ("orbit.eccentricity_j2000", "Earth orbital eccentricity at J2000",
     "эксцентриситет орбиты Земли (J2000)", 0.01671123, "1", 1e-8, "orbit", _JPL),
    ("orbit.year_sidereal", "sidereal year", "звёздный год", 365.256363004, "d",
     1e-8, "orbit", _IERS),
    ("orbit.year_tropical", "tropical year", "тропический год", 365.24219, "d",
     1e-5, "orbit", _IERS),
    ("orbit.year_anomalistic", "anomalistic year", "аномалистический год",
     365.259636, "d", 1e-5, "orbit", _IERS),
    ("orbit.perihelion_shift", "perihelion precession", "смещение перигелия",
     11.6, "arcsec per yr", 0.1, "orbit", "Laskar 1986"),
    ("orbit.mean_velocity", "Earth mean orbital speed", "средняя скорость Земли по орбите",
     29784.0, "m s-1", 1.0, "orbit", _JPL),

    # — Солнце —
    ("sun.mass", "Solar mass", "масса Солнца", 1.98841e30, "kg", 4e26, "sun", _JPL),
    ("sun.GM", "Solar gravitational parameter", "GM Солнца", 1.32712440041e20,
     "m3 s-2", 1e10, "sun", _JPL),
    ("sun.radius", "Solar radius (nominal)", "радиус Солнца", 6.957e8, "m", 0.0,
     "sun", _IAU),
    ("sun.luminosity", "Solar luminosity (nominal)", "светимость Солнца", 3.828e26,
     "W", 0.0, "sun", _IAU),
    ("sun.irradiance_tsi", "total solar irradiance at 1 au", "солнечная постоянная",
     1361.0, "W m-2", 0.5, "sun", "Kopp & Lean 2011, GRL 38, L01706"),
    ("sun.effective_temperature", "Solar effective temperature",
     "эффективная температура Солнца", 5772.0, "K", 0.8, "sun", _IAU),
    ("sun.age", "Solar age", "возраст Солнца", 4.567e9, "yr", 1e7, "sun",
     "Connelly et al. 2012, Science 338 (CAI age)"),
    ("sun.cycle_length", "sunspot cycle mean length", "средняя длина солнечного цикла",
     11.0, "yr", 2.0, "sun", "SILSO sunspot record"),
    ("sun.luminosity_growth", "solar luminosity growth rate",
     "рост светимости Солнца", 1.0, "percent per 110 Myr", 0.1, "sun",
     "Gough 1981, Sol. Phys. 74 (standard solar model)"),

    # — Луна —
    ("moon.mass", "Moon mass", "масса Луны", 7.346e22, "kg", 1e19, "moon", _JPL),
    ("moon.radius", "Moon mean radius", "средний радиус Луны", 1737400.0, "m", 100.0,
     "moon", "IAU/IAG Working Group 2011"),
    ("moon.distance_mean", "Moon mean distance", "среднее расстояние до Луны",
     384399000.0, "m", 1000.0, "moon", _JPL),
    ("moon.recession_rate", "lunar recession rate", "удаление Луны",
     0.0382, "m per yr", 0.0007, "moon", "Williams & Boggs 2016 (LLR)"),
    ("moon.month_synodic", "synodic month", "синодический месяц", 29.530588861, "d",
     1e-8, "moon", _IERS),
    ("moon.month_sidereal", "sidereal month", "сидерический месяц", 27.321661, "d",
     1e-6, "moon", _IERS),
    ("moon.month_draconic", "draconic month", "драконический месяц", 27.212221, "d",
     1e-6, "moon", _IERS),
    ("moon.saros", "Saros eclipse cycle", "сарос — цикл затмений", 6585.3211, "d",
     0.001, "moon", "NASA Eclipse Web Site (Espenak)"),
    ("moon.node_regression", "lunar node regression period",
     "период обращения лунных узлов", 18.612958, "yr", 1e-5, "moon", _IERS),

    # — Земля в Галактике —
    ("galaxy.r0_sun", "Sun distance to Galactic centre",
     "расстояние Солнца до центра Галактики", 8178.0, "pc", 26.0, "galaxy", _GRAV),
    ("galaxy.z0_sun", "Sun height above Galactic plane",
     "высота Солнца над плоскостью Галактики", 20.8, "pc", 0.3, "galaxy",
     "Bennett & Bovy 2019, MNRAS 482"),
    ("galaxy.v_circ", "local circular velocity", "круговая скорость на орбите Солнца",
     234.0, "km s-1", 3.0, "galaxy", "Reid et al. 2019 / GRAVITY 2019"),
    ("galaxy.year", "Galactic year", "галактический год", 2.25e8, "yr", 1.5e7,
     "galaxy", "derived from R0 and v_circ"),
    ("galaxy.apex_ra", "solar apex right ascension", "прямое восхождение апекса Солнца",
     277.0, "deg", 2.0, "galaxy", "Schönrich, Binney & Dehnen 2010"),
    ("galaxy.apex_dec", "solar apex declination", "склонение апекса Солнца",
     30.0, "deg", 2.0, "galaxy", "Schönrich, Binney & Dehnen 2010"),
    ("galaxy.v_lsr_u", "solar motion U (toward Galactic centre)",
     "движение Солнца относительно LSR, U", 11.1, "km s-1", 1.0, "galaxy",
     "Schönrich, Binney & Dehnen 2010"),
    ("galaxy.v_lsr_v", "solar motion V (direction of rotation)",
     "движение Солнца относительно LSR, V", 12.24, "km s-1", 2.0, "galaxy",
     "Schönrich, Binney & Dehnen 2010"),
    ("galaxy.v_lsr_w", "solar motion W (toward North Galactic Pole)",
     "движение Солнца относительно LSR, W", 7.25, "km s-1", 0.5, "galaxy",
     "Schönrich, Binney & Dehnen 2010"),
    ("galaxy.disk_scale_length", "Galactic disk scale length",
     "радиальная шкала галактического диска", 2600.0, "pc", 500.0, "galaxy",
     "Bland-Hawthorn & Gerhard 2016, ARA&A 54"),
    ("galaxy.mass_stellar", "Milky Way stellar mass", "звёздная масса Галактики",
     5.0e10, "Msun", 1.0e10, "galaxy", "Bland-Hawthorn & Gerhard 2016"),
    ("galaxy.ngp_ra", "North Galactic Pole RA (J2000)",
     "прямое восхождение северного полюса Галактики", 192.85948, "deg", 1e-4,
     "galaxy", "Hipparcos/ICRS convention"),
    ("galaxy.ngp_dec", "North Galactic Pole Dec (J2000)",
     "склонение северного полюса Галактики", 27.12825, "deg", 1e-4, "galaxy",
     "Hipparcos/ICRS convention"),
    ("galaxy.nearest_star_dist", "distance to Proxima Centauri",
     "расстояние до Проксимы Центавра", 1.30197, "pc", 2e-5, "galaxy",
     "Gaia DR3 parallax"),

    # — Вселенная вокруг —
    ("universe.age", "age of the Universe", "возраст Вселенной", 1.3787e10, "yr",
     2.0e7, "universe", _PLANCK),
    ("universe.h0_cmb", "Hubble constant (CMB)", "постоянная Хаббла по реликту",
     67.4, "km s-1 Mpc-1", 0.5, "universe", _PLANCK),
    ("universe.h0_cepheid", "Hubble constant (distance ladder)",
     "постоянная Хаббла по цефеидам", 73.0, "km s-1 Mpc-1", 1.0, "universe",
     "Riess et al. 2022, ApJL 934, L7 (расхождение с CMB не объяснено)"),
    ("universe.omega_m", "matter density parameter", "плотность материи Ω_m",
     0.315, "1", 0.007, "universe", _PLANCK),
    ("universe.omega_lambda", "dark energy density", "плотность тёмной энергии Ω_Λ",
     0.685, "1", 0.007, "universe", _PLANCK),
    ("universe.cmb_temperature", "CMB temperature", "температура реликтового излучения",
     2.72548, "K", 0.00057, "universe", "Fixsen 2009, ApJ 707"),
    ("universe.cmb_dipole_v", "solar system speed vs CMB",
     "скорость Солнечной системы относительно реликта", 369.82, "km s-1", 0.11,
     "universe", _PLANCK),
    ("universe.local_group_v", "Local Group speed vs CMB",
     "скорость Местной группы относительно реликта", 620.0, "km s-1", 15.0,
     "universe", "Kogut et al. 1993 / Planck 2018"),

    # — физика, без которой ничего не считается —
    ("phys.c", "speed of light in vacuum", "скорость света", 299792458.0, "m s-1",
     0.0, "physics", "SI (defined)"),
    ("phys.G", "gravitational constant", "гравитационная постоянная", 6.67430e-11,
     "m3 kg-1 s-2", 1.5e-15, "physics", "CODATA 2018"),
    ("phys.sigma_sb", "Stefan-Boltzmann constant", "постоянная Стефана — Больцмана",
     5.670374419e-8, "W m-2 K-4", 0.0, "physics", "CODATA 2018 (exact)"),
    ("phys.h", "Planck constant", "постоянная Планка", 6.62607015e-34, "J s", 0.0,
     "physics", "SI (defined)"),
    ("phys.k_b", "Boltzmann constant", "постоянная Больцмана", 1.380649e-23, "J K-1",
     0.0, "physics", "SI (defined)"),
]

# ── 2. Планеты: средние элементы орбит (Standish, JPL) ──────────────────────
# a (au), e, i (deg), L (deg), долгота перигелия (deg), долгота узла (deg)
# и их вековые скорости (на столетие) — эпоха J2000, точность ~arcmin на
# интервале 3000 до н. э. — 3000 н. э.
_STANDISH = "Standish 1992 / JPL «Keplerian Elements for Approximate Positions»"
PLANETS = [
    # name, a, a', e, e', i, i', L, L', wbar, wbar', node, node', radius_m, mass_kg
    ("Mercury", "Меркурий", 0.38709927, 0.00000037, 0.20563593, 0.00001906,
     7.00497902, -0.00594749, 252.25032350, 149472.67411175, 77.45779628,
     0.16047689, 48.33076593, -0.12534081, 2439700.0, 3.3011e23),
    ("Venus", "Венера", 0.72333566, 0.00000390, 0.00677672, -0.00004107,
     3.39467605, -0.00078890, 181.97909950, 58517.81538729, 131.60246718,
     0.00268329, 76.67984255, -0.27769418, 6051800.0, 4.8675e24),
    ("Earth", "Земля", 1.00000261, 0.00000562, 0.01671123, -0.00004392,
     -0.00001531, -0.01294668, 100.46457166, 35999.37244981, 102.93768193,
     0.32327364, 0.0, 0.0, 6371000.0, 5.97217e24),
    ("Mars", "Марс", 1.52371034, 0.00001847, 0.09339410, 0.00007882,
     1.84969142, -0.00813131, -4.55343205, 19140.30268499, -23.94362959,
     0.44441088, 49.55953891, -0.29257343, 3389500.0, 6.4171e23),
    ("Jupiter", "Юпитер", 5.20288700, -0.00011607, 0.04838624, -0.00013253,
     1.30439695, -0.00183714, 34.39644051, 3034.74612775, 14.72847983,
     0.21252668, 100.47390909, 0.20469106, 69911000.0, 1.8982e27),
    ("Saturn", "Сатурн", 9.53667594, -0.00125060, 0.05386179, -0.00050991,
     2.48599187, 0.00193609, 49.95424423, 1222.49362201, 92.59887831,
     -0.41897216, 113.66242448, -0.28867794, 58232000.0, 5.6834e26),
    ("Uranus", "Уран", 19.18916464, -0.00196176, 0.04725744, -0.00004397,
     0.77263783, -0.00242939, 313.23810451, 428.48202785, 170.95427630,
     0.40805281, 74.01692503, 0.04240589, 25362000.0, 8.6810e25),
    ("Neptune", "Нептун", 30.06992276, 0.00026291, 0.00859048, 0.00005105,
     1.77004347, 0.00035372, -55.12002969, 218.45945325, 44.96476227,
     -0.32241464, 131.78422574, -0.00508664, 24622000.0, 1.02409e26),
]


def _constants_chunk(man, out_dir) -> None:
    if man.chunk_done(NAME, "constants"):
        return
    recs = []
    for (cid, name, name_ru, value, unit, unc, domain, src) in CONSTANTS:
        r = schema.base_record("constant", src, "public-domain-fact", "K")
        r.update({"id": cid, "name": name, "name_ru": name_ru,
                  "value": float(value), "unit": unit,
                  "uncertainty": (float(unc) if unc is not None else None),
                  "domain": domain})
        recs.append(r)
    p = common.write_one_shard("constant", recs, out_dir, "constants_0000.parquet")
    man.mark_chunk(NAME, "constants", rows=len(recs), files=[p],
                   note="измеренные величины мира с указанием измерения")
    print(f"    astro: постоянных {len(recs)}")


def _planets_chunk(man, out_dir) -> None:
    if man.chunk_done(NAME, "planets"):
        return
    recs = []
    for row in PLANETS:
        (nm, nm_ru, a, da, e, de, inc, dinc, L, dL, wbar, dwbar,
         node, dnode, rad, mass) = row
        r = schema.base_record("sky_object", _STANDISH, "public-domain-gov", "K")
        r.update({"id": f"planet:{nm.lower()}", "kind_of": "planet", "name": nm,
                  "name_ru": nm_ru, "a_au": a, "a_rate": da, "ecc": e, "ecc_rate": de,
                  "inc_deg": inc, "inc_rate": dinc, "mean_long_deg": L,
                  "mean_long_rate": dL, "peri_long_deg": wbar, "peri_long_rate": dwbar,
                  "node_long_deg": node, "node_long_rate": dnode,
                  "radius_m": rad, "mass_kg": mass,
                  "ra_deg": None, "dec_deg": None, "mag": None,
                  "dist_pc": None, "spect": None})
        recs.append(r)
    p = common.write_one_shard("sky_object", recs, out_dir, "planets_0000.parquet")
    man.mark_chunk(NAME, "planets", rows=len(recs), files=[p],
                   note="кеплеровы элементы на эпоху J2000 со вековыми скоростями")


def _orbital_chunk(ctx, man, out_dir) -> None:
    """Решение Ласкара La2004: чем на самом деле управляются ледниковые эпохи."""
    if man.chunk_done(NAME, "orbital"):
        return
    ctx.check(90)
    path = common.download(ctx, LASKAR_URL, common.raw_path(NAME, "la2004.asc"))
    recs = []
    with open(path) as f:
        for line in f:
            parts = line.replace("D", "E").split()
            if len(parts) != 4:
                continue
            t_kyr, ecc, obl, peri = (float(x) for x in parts)
            year = int(round(t_kyr * 1000.0))
            for series, val, unit in (("eccentricity", ecc, "1"),
                                      ("obliquity", obl, "rad"),
                                      ("perihelion_longitude", peri, "rad")):
                r = schema.base_record("timeseries", LASKAR_SRC, LASKAR_LIC, "K")
                r.update({"series": f"earth_orbit.{series}", "t": year,
                          "t_unit": "year_from_J2000", "value": val, "unit": unit})
                recs.append(r)
    paths, n = common.write_shards("timeseries", recs, out_dir, "orbital", 400_000)
    man.mark_chunk(NAME, "orbital", rows=n, files=paths,
                   note="эксцентриситет/наклон оси/перигелий, 51 млн лет назад, шаг 1 тыс. лет")
    print(f"    astro: орбитальных значений {n}")
    common.drop_raw(NAME)


def _stars_chunk(ctx, man, out_dir) -> None:
    """Каталог HYG: настоящее небо, которое видели все наши предки."""
    if man.chunk_done(NAME, "stars"):
        return
    ctx.check(120)
    path = common.download(ctx, HYG_URL, common.raw_path(NAME, "hyg.csv"))
    recs = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            mag = common.to_float(row.get("mag"))
            if mag is None or mag > 7.5:
                continue          # глазом не видно и в телескоп эпохи тоже
            r = schema.base_record("sky_object", HYG_SRC, HYG_LIC, "K")
            name = (row.get("proper") or row.get("bf") or row.get("gl")
                    or f"HYG {row['id']}").strip()
            r.update({
                "id": f"star:{row['id']}", "kind_of": "star", "name": name,
                "name_ru": None,
                "hip": common.to_float(row.get("hip")),
                "ra_deg": (common.to_float(row.get("ra")) or 0.0) * 15.0,
                "dec_deg": common.to_float(row.get("dec")),
                "dist_pc": common.to_float(row.get("dist")),
                "mag": mag, "absmag": common.to_float(row.get("absmag")),
                "spect": (row.get("spect") or None),
                "ci": common.to_float(row.get("ci")),
                "pm_ra_masyr": common.to_float(row.get("pmra")),
                "pm_dec_masyr": common.to_float(row.get("pmdec")),
                "rv_kms": common.to_float(row.get("rv")),
                "constellation": (row.get("con") or None),
                "bayer": (row.get("bayer") or None),
                "lum_sun": common.to_float(row.get("lum")),
            })
            recs.append(r)
    paths, n = common.write_shards("sky_object", recs, out_dir, "stars", 200_000)
    man.mark_chunk(NAME, "stars", rows=n, files=paths,
                   note="HYG v4.1, звёзды ярче 7.5m — всё, что вообще видно с Земли")
    print(f"    astro: звёзд {n}")
    common.drop_raw(NAME)


def _figures_chunk(ctx, man, out_dir) -> None:
    """Линии созвездий: как небо было РАЗМЕЧЕНО людьми (традиция, не измерение)."""
    if man.chunk_done(NAME, "figures"):
        return
    ctx.check(45)
    path = common.download(ctx, FIG_URL, common.raw_path(NAME, "lines.json"))
    with open(path, encoding="utf-8") as f:
        gj = json.load(f)
    recs = []
    for feat in gj.get("features", []):
        props = feat.get("properties", {})
        geom = feat.get("geometry", {})
        cid = props.get("id") or props.get("name") or "?"
        segs = geom.get("coordinates", [])
        if geom.get("type") == "LineString":
            segs = [segs]
        for k, seg in enumerate(segs):
            r = schema.base_record("sky_object", FIG_SRC, FIG_LIC, "T")
            r.update({"id": f"figure:{cid}:{k}", "kind_of": "constellation_line",
                      "name": str(props.get("name") or cid), "name_ru": None,
                      "constellation": str(cid),
                      "path_ra_dec": json.dumps(seg, separators=(",", ":")),
                      "ra_deg": None, "dec_deg": None, "mag": None,
                      "dist_pc": None, "spect": None})
            recs.append(r)
    if recs:
        p = common.write_one_shard("sky_object", recs, out_dir, "figures_0000.parquet")
        man.mark_chunk(NAME, "figures", rows=len(recs), files=[p],
                       note="линии созвездий современной западной традиции")
        print(f"    astro: линий созвездий {len(recs)}")
    common.drop_raw(NAME)


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    _constants_chunk(man, out_dir)
    _planets_chunk(man, out_dir)
    _orbital_chunk(ctx, man, out_dir)
    _stars_chunk(ctx, man, out_dir)
    _figures_chunk(ctx, man, out_dir)

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, HOME, LICENSE, TITLE,
            "Небо и место Земли во Вселенной: измеренные постоянные (Земля, Солнце, "
            "Луна, Галактика, космология), решение Ласкара La2004 (циклы Миланковича "
            "на 51 млн лет), каталог звёзд HYG v4.1, линии созвездий, кеплеровы "
            "элементы планет. Нужно, чтобы небо над людьми симуляции было тем же, "
            "что над нами: год, календарь, навигация и прецессия — настоящие.",
            tier="K")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "постоянные, орбита, звёзды, созвездия, планеты"}
