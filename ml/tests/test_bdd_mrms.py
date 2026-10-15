import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts" / "bdd"))
from nucleo import classe_de, decidir, gps_no_instante, mrms_valido, timestamp_mrms_mais_proximo, url_mrms
import mrms


def utc(*a):
    return datetime(*a, tzinfo=timezone.utc)


def test_limiares():
    assert [classe_de(x) for x in (0, 0.01, 2.5, 2.51, 10, 10.01)] == \
        ["seco", "garoa", "garoa", "moderada", "moderada", "forte"]


def test_mrms_valido():
    assert mrms_valido(-3) is None and mrms_valido(-1) is None and mrms_valido(None) is None
    assert mrms_valido(0) == 0.0 and mrms_valido(4.2) == 4.2


def test_timestamp_mais_proximo():
    assert timestamp_mrms_mais_proximo(utc(2017, 3, 5, 19, 0, 29)) == utc(2017, 3, 5, 19, 0)
    assert timestamp_mrms_mais_proximo(utc(2017, 3, 5, 19, 1, 1)) == utc(2017, 3, 5, 19, 2)
    assert timestamp_mrms_mais_proximo(utc(2017, 3, 5, 19, 2, 59)) == utc(2017, 3, 5, 19, 2)
    assert timestamp_mrms_mais_proximo(utc(2017, 3, 5, 19, 3, 5)) == utc(2017, 3, 5, 19, 4)
    assert timestamp_mrms_mais_proximo(utc(2017, 3, 5, 23, 59, 40)) == utc(2017, 3, 6, 0, 0)


def test_url():
    assert url_mrms(utc(2017, 3, 5, 19, 0)).endswith("2017/03/05/mrms/ncep/PrecipRate/PrecipRate_00.00_20170305-190000.grib2.gz")


LOC = [dict(timestamp=1000, latitude=10.0, longitude=20.0, speed=5),
       dict(timestamp=2000, latitude=11.0, longitude=22.0, speed=7)]


def test_gps_interpola():
    assert gps_no_instante(LOC, 1500) == (10.5, 21.0, 5)
    assert gps_no_instante(LOC, 2000)[:2] == (11.0, 22.0)


def test_gps_sem_fix():
    assert gps_no_instante([], 1500) is None
    assert gps_no_instante(LOC, 9000) is None          # longe do último fix
    assert gps_no_instante(LOC, 3500)[:2] == (11.0, 22.0)  # dentro da tolerância
    gap = [dict(timestamp=0, latitude=1, longitude=1), dict(timestamp=20000, latitude=2, longitude=2)]
    assert gps_no_instante(gap, 10000) is None          # buraco grande: não inventa


def test_decidir_seco():
    z = [0.0] * 9
    assert decidir(0.0, z, [0.0, 0.0], [0.0, 0.0], [0.0]) == ("seco", False, "")
    assert decidir(0.0, z[:8] + [0.3], [0.0, 0.0], [0.0, 0.0])[1] is True
    assert decidir(0.0, z, [0.0, None], [0.0, 0.0])[1] is True
    assert decidir(0.0, z, [0.0, 0.0], [0.0, 0.0], [0.0, 1.0])[1] is True


def test_decidir_chuva():
    assert decidir(5.0, [4, 5, 6, 5, 5, 7, 8, 5, 5], [5.5, 6.0], [5, 5]) == ("moderada", False, "")
    assert decidir(5.0, [1, 5, 6, 5, 5, 7, 8, 5, 5], [5.5, 6.0], [5, 5])[2] == "vizinhanca_heterogenea"
    assert decidir(5.0, [5.0] * 9, [5.5, 12.0], [5, 5])[2] == "instavel_2min"
    assert decidir(None, [], [], [])[0] is None


def test_indice_grade():
    assert mrms.indice(37.75, -122.4) is not None
    assert mrms.indice(60.0, -122.4) is None          # fora do CONUS
    i, j = mrms.indice(37.75, -122.4)
    assert abs(54.995 - i * 0.01 - 37.75) <= 0.006 and abs(230.005 + j * 0.01 - (360 - 122.4)) <= 0.006
