extends SceneTree
## Headless test runner:
##   /opt/Godot4/Godot_v4.7-stable_linux.x86_64 --headless --path . --script tests/run_tests.gd
## Pure-logic tests over the simulation core. Exits nonzero on failure.

const PlotSimC = preload("res://src/sim/plot_sim.gd")
const WeatherModelC = preload("res://src/sim/weather_model.gd")
const CropDBC = preload("res://src/sim/crop_db.gd")
const QualitativeC = preload("res://src/sim/qualitative.gd")

var failures := 0
var checks := 0

func _initialize() -> void:
	test_weather_determinism()
	test_weather_variety_and_forecast()
	test_sandy_dries_faster_than_clay()
	test_clay_waterlogs_in_heavy_rain_sandy_drains()
	test_mulch_slows_drying()
	test_cover_sheds_rain()
	test_frost_kills_tomato_spares_cabbage_cover_protects()
	test_crop_grows_to_maturity_and_yields()
	test_neglect_reduces_yield_quality()
	test_manure_burns_young_plants()
	test_potato_rots_in_soaked_clay()
	test_heat_hurts_cabbage_not_tomato()
	test_wilt_and_qualitative_text()

	print("")
	if failures == 0:
		print("ALL TESTS PASSED (%d checks)" % checks)
		quit(0)
	else:
		print("%d FAILURES out of %d checks" % [failures, checks])
		quit(1)

func check(cond: bool, label: String) -> void:
	checks += 1
	if cond:
		print("  ok   %s" % label)
	else:
		failures += 1
		print("  FAIL %s" % label)

func header(name: String) -> void:
	print("\n== %s" % name)

# ---------------------------------------------------------------- helpers

## Environment presets.
func env_sunny_warm() -> Dictionary:
	return {"temp": 24.0, "raining": false, "rain_rate": 0.0, "sun": 0.9}

func env_night_mild() -> Dictionary:
	return {"temp": 10.0, "raining": false, "rain_rate": 0.0, "sun": 0.0}

func env_heavy_rain() -> Dictionary:
	return {"temp": 13.0, "raining": true, "rain_rate": 0.24, "sun": 0.1}

func env_frost(temp: float = -3.0) -> Dictionary:
	return {"temp": temp, "raining": false, "rain_rate": 0.0, "sun": 0.0}

## Run a plot through n "days" of a simple day/night cycle.
func run_days(p, n_days: int, day_env: Dictionary, night_env: Dictionary) -> void:
	for i in n_days:
		for h in 14:
			p.tick(1.0, day_env)
		for h in 10:
			p.tick(1.0, night_env)
		p.end_of_day()

# ---------------------------------------------------------------- tests

func test_weather_determinism() -> void:
	header("weather: deterministic per seed")
	var a = WeatherModelC.new(42)
	var b = WeatherModelC.new(42)
	var c = WeatherModelC.new(43)
	a.ensure_generated(20)
	b.ensure_generated(20)
	c.ensure_generated(20)
	var same := true
	for i in 20:
		if str(a.day(i)) != str(b.day(i)):
			same = false
	check(same, "same seed -> identical 20 days")
	var diff := false
	for i in 20:
		if str(a.day(i)) != str(c.day(i)):
			diff = true
	check(diff, "different seed -> different days")

func test_weather_variety_and_forecast() -> void:
	header("weather: variety and forecast calibration")
	var m = WeatherModelC.new(7)
	m.ensure_generated(200)
	var seen := {}
	var frost_nights := 0
	var rain_days := 0
	for i in 200:
		var d = m.day(i)
		seen[d["pattern"]] = true
		if d["t_night"] <= 0.0:
			frost_nights += 1
		if d["rain_rate"] > 0.0:
			rain_days += 1
	check(seen.size() >= 5, "at least 5 distinct patterns in 200 days (saw %d)" % seen.size())
	check(frost_nights >= 8 and frost_nights <= 70, "frost nights plausible (%d/200)" % frost_nights)
	check(rain_days >= 30 and rain_days <= 120, "rain days plausible (%d/200)" % rain_days)
	# Forecast calibration: high-frost-chance forecasts should freeze much more
	# often than low-chance ones.
	var hi_hits := 0; var hi_total := 0
	var lo_hits := 0; var lo_total := 0
	for i in 200:
		var f = m.forecast_for(i)
		var actual_frost: bool = m.day(i)["t_night"] <= 0.0
		if f["frost_chance"] >= 0.5:
			hi_total += 1
			if actual_frost: hi_hits += 1
		elif f["frost_chance"] < 0.1:
			lo_total += 1
			if actual_frost: lo_hits += 1
	check(hi_total > 0 and float(hi_hits) / hi_total > 0.7, "high frost forecasts mostly freeze (%d/%d)" % [hi_hits, hi_total])
	check(lo_total > 0 and float(lo_hits) / lo_total < 0.1, "low frost forecasts rarely freeze (%d/%d)" % [lo_hits, lo_total])
	# Uncertainty really exists: some warned nights don't freeze.
	var warned_no_frost := 0
	for i in 200:
		var f2 = m.forecast_for(i)
		if f2["frost_chance"] >= 0.3 and m.day(i)["t_night"] > 0.0:
			warned_no_frost += 1
	check(warned_no_frost > 0, "some frost warnings are false alarms (%d)" % warned_no_frost)

func test_sandy_dries_faster_than_clay() -> void:
	header("soil: sandy dries out first in sun")
	var sandy = PlotSimC.new(PlotSimC.Soil.SANDY)
	var loam = PlotSimC.new(PlotSimC.Soil.LOAM)
	var clay = PlotSimC.new(PlotSimC.Soil.CLAY)
	for p in [sandy, loam, clay]:
		p.moisture = 0.55
	run_days(sandy, 2, env_sunny_warm(), env_night_mild())
	run_days(loam, 2, env_sunny_warm(), env_night_mild())
	run_days(clay, 2, env_sunny_warm(), env_night_mild())
	check(sandy.moisture < loam.moisture and loam.moisture < clay.moisture,
		"after 2 sunny days: sandy %.2f < loam %.2f < clay %.2f" % [sandy.moisture, loam.moisture, clay.moisture])
	check(sandy.moisture < 0.25, "sandy is nearly dry (%.2f)" % sandy.moisture)

func test_clay_waterlogs_in_heavy_rain_sandy_drains() -> void:
	header("soil: heavy rain waterlogs clay but drains from sandy")
	var sandy = PlotSimC.new(PlotSimC.Soil.SANDY)
	var clay = PlotSimC.new(PlotSimC.Soil.CLAY)
	sandy.moisture = 0.5; clay.moisture = 0.5
	# 6 hours of heavy rain
	for h in 6:
		sandy.tick(1.0, env_heavy_rain())
		clay.tick(1.0, env_heavy_rain())
	check(clay.moisture > 0.85, "clay saturated after heavy rain (%.2f)" % clay.moisture)
	# then 18h no rain
	for h in 8:
		sandy.tick(1.0, env_sunny_warm())
		clay.tick(1.0, env_sunny_warm())
	for h in 10:
		sandy.tick(1.0, env_night_mild())
		clay.tick(1.0, env_night_mild())
	check(sandy.moisture < 0.7, "sandy drained back down within a day (%.2f)" % sandy.moisture)
	check(clay.moisture > 0.85, "clay still waterlogged a day later (%.2f)" % clay.moisture)

func test_mulch_slows_drying() -> void:
	header("amendments: mulch slows moisture loss")
	var bare = PlotSimC.new(PlotSimC.Soil.SANDY)
	var mulched = PlotSimC.new(PlotSimC.Soil.SANDY)
	bare.moisture = 0.5; mulched.moisture = 0.5
	mulched.apply_mulch()
	run_days(bare, 1, env_sunny_warm(), env_night_mild())
	run_days(mulched, 1, env_sunny_warm(), env_night_mild())
	check(mulched.moisture > bare.moisture + 0.08,
		"mulched kept clearly more water (%.2f vs %.2f)" % [mulched.moisture, bare.moisture])

func test_cover_sheds_rain() -> void:
	header("amendments: row cover sheds most rain")
	var open_plot = PlotSimC.new(PlotSimC.Soil.LOAM)
	var covered = PlotSimC.new(PlotSimC.Soil.LOAM)
	open_plot.moisture = 0.4; covered.moisture = 0.4
	covered.set_cover(true)
	for h in 5:
		open_plot.tick(1.0, env_heavy_rain())
		covered.tick(1.0, env_heavy_rain())
	check(covered.moisture < open_plot.moisture - 0.1,
		"covered plot stayed drier (%.2f vs %.2f)" % [covered.moisture, open_plot.moisture])

func test_frost_kills_tomato_spares_cabbage_cover_protects() -> void:
	header("frost: tomato dies, cabbage shrugs, cover saves")
	var tom = PlotSimC.new(PlotSimC.Soil.LOAM); tom.plant("tomato"); tom.growth = 0.6
	var tom_covered = PlotSimC.new(PlotSimC.Soil.LOAM); tom_covered.plant("tomato"); tom_covered.growth = 0.6
	tom_covered.set_cover(true)
	var cab = PlotSimC.new(PlotSimC.Soil.LOAM); cab.plant("cabbage"); cab.growth = 0.6
	# a 3-hour pre-dawn frost at -3 C
	for h in 3:
		tom.tick(1.0, env_frost(-3.0))
		tom_covered.tick(1.0, env_frost(-3.0))
		cab.tick(1.0, env_frost(-3.0))
	check(tom.dead, "uncovered tomato died in -3C frost (health %.2f)" % tom.health)
	check(not tom_covered.dead and tom_covered.health > 0.7,
		"covered tomato survived fine (health %.2f)" % tom_covered.health)
	check(not cab.dead and cab.health > 0.85, "cabbage barely noticed (health %.2f)" % cab.health)
	# a light frost at -0.5 C wounds but shouldn't kill a tomato in 2h
	var tom2 = PlotSimC.new(PlotSimC.Soil.LOAM); tom2.plant("tomato"); tom2.growth = 0.6
	for h in 2:
		tom2.tick(1.0, env_frost(-0.5))
	check(not tom2.dead and tom2.health < 0.95,
		"light frost wounds tomato without killing (health %.2f)" % tom2.health)
	check(tom2.frostbitten > 0.1, "light frost leaves visible frostbite")

func test_crop_grows_to_maturity_and_yields() -> void:
	header("growth: cared-for wheat matures in a sensible time")
	var p = PlotSimC.new(PlotSimC.Soil.LOAM)
	p.plant("wheat")
	var days := 0
	while not p.mature() and days < 30:
		for h in 14:
			p.tick(1.0, env_sunny_warm())
			if p.moisture < 0.3:
				p.water()
		for h in 10:
			p.tick(1.0, env_night_mild())
		p.end_of_day()
		days += 1
	check(p.mature(), "wheat reached maturity")
	check(days >= 4 and days <= 12, "took a plausible %d days (target ~5-9)" % days)
	var coins := p.harvest()
	check(coins >= 20, "healthy harvest paid well (%d coins)" % coins)
	check(p.crop_id == "", "plot empty after harvest")

func test_neglect_reduces_yield_quality() -> void:
	header("growth: a stressed crop pays less than a cared-for one")
	var good = PlotSimC.new(PlotSimC.Soil.LOAM); good.plant("tomato")
	var bad = PlotSimC.new(PlotSimC.Soil.SANDY); bad.plant("tomato")
	var days := 0
	while days < 25 and not (good.mature() and (bad.mature() or bad.dead)):
		for h in 14:
			good.tick(1.0, env_sunny_warm())
			bad.tick(1.0, env_sunny_warm())
			if good.moisture < 0.4:
				good.water()
			# bad: only watered when badly wilted, on hungry sandy soil
			if bad.moisture < 0.12:
				bad.water()
		for h in 10:
			good.tick(1.0, env_night_mild())
			bad.tick(1.0, env_night_mild())
		good.end_of_day(); bad.end_of_day()
		days += 1
	check(good.mature(), "cared-for tomato matured")
	if bad.dead:
		check(true, "neglected tomato died outright")
	else:
		var g := good.harvest()
		var b := bad.harvest() if bad.mature() else 0
		check(b < g, "neglected yield worth less (%d vs %d)" % [b, g])

func test_manure_burns_young_plants() -> void:
	header("amendments: manure scorches seedlings but feeds strongly")
	var young = PlotSimC.new(PlotSimC.Soil.SANDY)
	young.plant("cabbage")
	young.growth = 0.2
	var before: float = young.health
	var result: String = young.apply_manure()
	check(result == "burned" and young.health < before, "manure burned the seedling")
	check(young.fertility > 0.6, "but fertility jumped (%.2f)" % young.fertility)
	var older = PlotSimC.new(PlotSimC.Soil.SANDY)
	older.plant("cabbage")
	older.growth = 0.7
	var before2: float = older.health
	check(older.apply_manure() == "ok" and older.health == before2, "established plant unharmed")

func test_potato_rots_in_soaked_clay() -> void:
	header("emergence: potatoes rot in waterlogged clay, cabbage copes")
	var spud = PlotSimC.new(PlotSimC.Soil.CLAY); spud.plant("potato"); spud.growth = 0.5
	var cab = PlotSimC.new(PlotSimC.Soil.CLAY); cab.plant("cabbage"); cab.growth = 0.5
	# two days of rain onto clay
	for d in 2:
		for h in 8:
			spud.tick(1.0, env_heavy_rain())
			cab.tick(1.0, env_heavy_rain())
		for h in 16:
			spud.tick(1.0, {"temp": 12.0, "raining": false, "rain_rate": 0.0, "sun": 0.2})
			cab.tick(1.0, {"temp": 12.0, "raining": false, "rain_rate": 0.0, "sun": 0.2})
	check(spud.health < 0.5, "potato suffering badly in soaked clay (health %.2f)" % spud.health)
	check(cab.health > spud.health + 0.2, "cabbage coping much better (health %.2f)" % cab.health)

func test_heat_hurts_cabbage_not_tomato() -> void:
	header("emergence: heat wave stresses cabbage, tomato enjoys it")
	var cab = PlotSimC.new(PlotSimC.Soil.LOAM); cab.plant("cabbage"); cab.growth = 0.5
	var tom = PlotSimC.new(PlotSimC.Soil.LOAM); tom.plant("tomato"); tom.growth = 0.5
	var heat := {"temp": 33.0, "raining": false, "rain_rate": 0.0, "sun": 1.0}
	for h in 10:
		cab.tick(1.0, heat)
		tom.tick(1.0, heat)
		# keep both watered so only heat differs
		if cab.moisture < 0.5: cab.water()
		if tom.moisture < 0.5: tom.water()
	check(cab.health < 0.95, "cabbage stressed by 33C (health %.2f)" % cab.health)
	check(tom.health > cab.health, "tomato handled it better (health %.2f)" % tom.health)

func test_wilt_and_qualitative_text() -> void:
	header("information: wilt is visible and text stays qualitative")
	var p = PlotSimC.new(PlotSimC.Soil.SANDY)
	p.plant("tomato")
	p.moisture = 0.5
	check(p.wilt_level() < 0.1, "well-watered tomato not wilting")
	p.moisture = 0.15
	check(p.wilt_level() > 0.3, "dry tomato visibly wilting (%.2f)" % p.wilt_level())
	var report: String = QualitativeC.crop_report(p)
	check("wilt" in report.to_lower(), "report mentions wilting: '%s'" % report)
	var digits := false
	for token in ["0.", "%", "="]:
		if token in report:
			digits = true
	check(not digits, "report contains no raw numbers")
	var feel: String = QualitativeC.soil_feel(p)
	check("gritty" in feel or "sandy" in feel.to_lower(), "soil feel describes sand: '%s'" % feel)
