class_name WeatherModel
extends RefCounted
## Generates daily weather from a small Markov chain of "patterns", plus an
## imperfect forecast for the next day. Deterministic for a given seed.
##
## A day record:
##   pattern: one of PATTERNS
##   t_day:   afternoon high (C)
##   t_night: pre-dawn low (C), reached around 05:00 of the *following* morning
##   rain_rate: soil-moisture units per hour while raining
##   rain_start_h / rain_end_h: hour window of rain (may be 0-length)
##   cloud:   0..1 (dims sun, reduces evaporation)

enum { CLEAR, HOT_DRY, OVERCAST, RAIN, HEAVY_RAIN, COLD_SNAP }

const PATTERN_NAMES := {
	CLEAR: "clear", HOT_DRY: "hot_dry", OVERCAST: "overcast",
	RAIN: "rain", HEAVY_RAIN: "heavy_rain", COLD_SNAP: "cold_snap",
}

# Markov transition table: pattern -> array of [next_pattern, weight].
const TRANSITIONS := {
	CLEAR:      [[CLEAR, 34], [HOT_DRY, 16], [OVERCAST, 26], [RAIN, 10], [COLD_SNAP, 14]],
	HOT_DRY:    [[HOT_DRY, 42], [CLEAR, 30], [OVERCAST, 18], [RAIN, 10]],
	OVERCAST:   [[OVERCAST, 22], [RAIN, 30], [CLEAR, 22], [HEAVY_RAIN, 12], [COLD_SNAP, 14]],
	RAIN:       [[RAIN, 22], [OVERCAST, 24], [CLEAR, 22], [HEAVY_RAIN, 20], [COLD_SNAP, 12]],
	HEAVY_RAIN: [[RAIN, 30], [OVERCAST, 30], [HEAVY_RAIN, 16], [CLEAR, 12], [COLD_SNAP, 12]],
	COLD_SNAP:  [[COLD_SNAP, 30], [CLEAR, 34], [OVERCAST, 26], [RAIN, 10]],
}

var rng := RandomNumberGenerator.new()
var days: Array[Dictionary] = []
var forecasts: Array[Dictionary] = []  # forecast[i] is about day i (issued day i-1)

func _init(seed_value: int = 1337) -> void:
	rng.seed = seed_value

func _pick_transition(from_pattern: int) -> int:
	var options: Array = TRANSITIONS[from_pattern]
	var total := 0
	for o in options:
		total += o[1]
	var roll := rng.randi_range(1, total)
	for o in options:
		roll -= o[1]
		if roll <= 0:
			return o[0]
	return CLEAR

func _generate_day(index: int) -> Dictionary:
	var pattern: int
	if index == 0:
		pattern = CLEAR  # gentle first day
	else:
		pattern = _pick_transition(days[index - 1]["pattern"])

	var d := {"pattern": pattern}
	match pattern:
		CLEAR:
			d["t_day"] = rng.randf_range(20.0, 26.0)
			d["t_night"] = rng.randf_range(7.0, 12.0)
			d["cloud"] = rng.randf_range(0.0, 0.25)
			d["rain_rate"] = 0.0
		HOT_DRY:
			d["t_day"] = rng.randf_range(31.0, 38.0)
			d["t_night"] = rng.randf_range(15.0, 20.0)
			d["cloud"] = rng.randf_range(0.0, 0.1)
			d["rain_rate"] = 0.0
		OVERCAST:
			d["t_day"] = rng.randf_range(14.0, 20.0)
			d["t_night"] = rng.randf_range(6.0, 10.0)
			d["cloud"] = rng.randf_range(0.6, 0.95)
			d["rain_rate"] = 0.0
		RAIN:
			d["t_day"] = rng.randf_range(12.0, 18.0)
			d["t_night"] = rng.randf_range(6.0, 10.0)
			d["cloud"] = rng.randf_range(0.7, 1.0)
			d["rain_rate"] = rng.randf_range(0.05, 0.10)
		HEAVY_RAIN:
			d["t_day"] = rng.randf_range(10.0, 16.0)
			d["t_night"] = rng.randf_range(5.0, 9.0)
			d["cloud"] = rng.randf_range(0.85, 1.0)
			d["rain_rate"] = rng.randf_range(0.18, 0.30)
		COLD_SNAP:
			d["t_day"] = rng.randf_range(6.0, 12.0)
			# Roughly 60% of cold snap nights actually freeze.
			if rng.randf() < 0.6:
				d["t_night"] = rng.randf_range(-5.0, -1.0)
			else:
				d["t_night"] = rng.randf_range(0.5, 4.0)
			d["cloud"] = rng.randf_range(0.1, 0.5)
			d["rain_rate"] = 0.0

	if d["rain_rate"] > 0.0:
		var start := rng.randf_range(6.0, 16.0)
		d["rain_start_h"] = start
		d["rain_end_h"] = start + rng.randf_range(3.0, 8.0)
	else:
		d["rain_start_h"] = 0.0
		d["rain_end_h"] = 0.0
	return d

func _make_forecast(tonight: Dictionary, tomorrow: Dictionary) -> Dictionary:
	## The forecast shown during a given day: frost odds are about TONIGHT's
	## pre-dawn low (this day's t_night); pattern/rain are about TOMORROW's
	## daytime. Imperfect: usually right, with honest-but-noisy probabilities.
	var f := {}
	var about := tomorrow
	var frost_actual: bool = tonight["t_night"] <= 0.0
	var cold_night: bool = tonight["t_night"] < 3.0
	var rain_actual: bool = about["rain_rate"] > 0.0
	var heavy_actual: bool = about["pattern"] == HEAVY_RAIN

	# Announced pattern: 78% truthful, else a plausible neighbour.
	var announced: int = about["pattern"]
	if rng.randf() > 0.78:
		match about["pattern"]:
			CLEAR: announced = [OVERCAST, HOT_DRY][rng.randi_range(0, 1)]
			HOT_DRY: announced = CLEAR
			OVERCAST: announced = [CLEAR, RAIN][rng.randi_range(0, 1)]
			RAIN: announced = [OVERCAST, HEAVY_RAIN][rng.randi_range(0, 1)]
			HEAVY_RAIN: announced = RAIN
			COLD_SNAP: announced = [OVERCAST, CLEAR][rng.randi_range(0, 1)]
	f["pattern"] = announced

	# Bands deliberately overlap at their boundaries: a forecast number alone
	# must never let the player back out the true outcome. "Frost (60%)"
	# sometimes doesn't freeze; a quiet "Frost (35%)" sometimes does.
	if frost_actual:
		f["frost_chance"] = rng.randf_range(0.3, 0.85)
	elif cold_night or tonight["pattern"] == COLD_SNAP:
		f["frost_chance"] = rng.randf_range(0.15, 0.65)
	else:
		f["frost_chance"] = rng.randf_range(0.0, 0.2)

	if rain_actual:
		f["rain_chance"] = rng.randf_range(0.4, 0.9)
		f["heavy"] = heavy_actual and rng.randf() < 0.8
	elif about["cloud"] > 0.5:
		f["rain_chance"] = rng.randf_range(0.15, 0.55)
		f["heavy"] = false
	else:
		f["rain_chance"] = rng.randf_range(0.0, 0.15)
		f["heavy"] = false
	return f

## Days and forecasts are generated in lockstep, one calendar day at a time,
## so the RNG stream -- and therefore every day/forecast past this point --
## is identical regardless of whether the caller asks for one day at a time
## or jumps straight to day_index. Generating days first and forecasts after
## (in two separate passes) would make the sequence depend on query
## granularity and break determinism for a given seed.
func ensure_generated(day_index: int) -> void:
	while days.size() <= day_index + 2 or forecasts.size() <= day_index:
		if forecasts.size() < days.size() - 1 and forecasts.size() <= day_index:
			var i := forecasts.size()
			forecasts.append(_make_forecast(days[i], days[i + 1]))
		else:
			days.append(_generate_day(days.size()))

func day(day_index: int) -> Dictionary:
	ensure_generated(day_index)
	return days[day_index]

## The forecast the player sees during day_index (tonight's frost odds +
## tomorrow's daytime pattern).
func forecast_for(day_index: int) -> Dictionary:
	ensure_generated(day_index)
	return forecasts[day_index]

## Continuous conditions at a moment. hour is 0..24 within day_index.
## Night low belongs to the pre-dawn of the FOLLOWING calendar day, so hours
## 0..7 blend from the previous day's records toward this day's low.
func conditions_at(day_index: int, hour: float) -> Dictionary:
	ensure_generated(day_index)
	var d := day(day_index)
	var temp := _temperature_at(day_index, hour)
	var raining: bool = d["rain_rate"] > 0.0 and hour >= d["rain_start_h"] and hour < d["rain_end_h"]
	var sun := 0.0
	if hour > 6.0 and hour < 20.0:
		sun = sin((hour - 6.0) / 14.0 * PI)
	sun *= 1.0 - 0.75 * float(d["cloud"])
	return {
		"temp": temp,
		"raining": raining,
		"rain_rate": d["rain_rate"] if raining else 0.0,
		"sun": maxf(sun, 0.0),
		"cloud": d["cloud"],
		"pattern": d["pattern"],
	}

func _temperature_at(day_index: int, hour: float) -> float:
	# Piecewise: low at 05:00 (this day's own low is the coming pre-dawn,
	# i.e. hours 24..29 == next day 0..5), high at 15:00.
	var today := day(day_index)
	var high: float = today["t_day"]
	if hour >= 5.0 and hour <= 15.0:
		# rise from this morning's low (previous day's t_night) to today's high
		var low: float = today["t_night"] if day_index == 0 else day(day_index - 1)["t_night"]
		var t := (hour - 5.0) / 10.0
		return lerpf(low, high, sin(t * PI * 0.5))
	elif hour > 15.0:
		# fall from today's high toward tonight's low (reached 05:00 tomorrow)
		var low_next: float = today["t_night"]
		var t2 := (hour - 15.0) / 14.0
		return lerpf(high, low_next, sin(t2 * PI * 0.5))
	else:
		# 00:00..05:00 -- still falling to this day's OWN pre-dawn low? No:
		# by our convention day N's t_night happens at 05:00 of day N+1, so
		# early hours of day N belong to day N-1's t_night.
		var low_prev: float = today["t_night"] if day_index == 0 else day(day_index - 1)["t_night"]
		var evening_high: float = today["t_day"] if day_index == 0 else day(day_index - 1)["t_day"]
		var t3 := (9.0 + hour) / 14.0  # continues the fall started at 15:00 yesterday
		return lerpf(evening_high, low_prev, sin(t3 * PI * 0.5))

func pattern_name(p: int) -> String:
	return PATTERN_NAMES.get(p, "clear")
