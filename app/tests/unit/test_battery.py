"""Battery gauge logic against a fake power_supply tree (no display)."""

from leo_kiosk.ui.battery import GAUGE_HEIGHT, GAUGE_WIDTH, read_battery


def make_supply(tmp_path, name="BAT1", type_="Battery", capacity="85", status="Discharging"):
    base = tmp_path / name
    base.mkdir()
    (base / "type").write_text(type_)
    (base / "capacity").write_text(capacity)
    (base / "status").write_text(status)
    return str(tmp_path)


def test_read_battery_returns_capacity_and_charging(tmp_path):
    root = make_supply(tmp_path)
    assert read_battery(root) == (85, False)


def test_read_battery_detects_charging_and_full(tmp_path):
    # read_battery returns the first battery in sorted order.
    assert read_battery(make_supply(tmp_path, name="BAT1", status="Charging", capacity="85")) == (85, True)
    other = tmp_path / "second"
    other.mkdir()
    assert read_battery(make_supply(other, name="AA", status="Full", capacity="90")) == (90, True)


def test_read_battery_skips_non_battery_and_malformed(tmp_path):
    root = make_supply(tmp_path, name="AC", type_="Mains", capacity="0", status="Unknown")
    (tmp_path / "BAT9").mkdir()
    (tmp_path / "BAT9" / "type").write_text("Battery")
    # capacity file missing -> entry skipped, no crash, None overall here
    assert read_battery(root) is None


def test_read_battery_without_directory_is_none(tmp_path):
    assert read_battery(str(tmp_path / "missing")) is None


def test_gauge_geometry_constants():
    assert GAUGE_WIDTH == 120
    assert GAUGE_HEIGHT == 25