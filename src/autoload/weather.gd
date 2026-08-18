extends Node
## Thin autoload wrapper around WeatherModel, indexed by the game clock.
## Day N's night low is reached around 05:00 of calendar day N+1, which is
## exactly what the evening forecast warns about.

var model := WeatherModel.new(11361)

func _ready() -> void:
	# A varied seed per run, unless RED_VALLEY_SEED is set (tests/repro).
	var env_seed := OS.get_environment("RED_VALLEY_SEED")
	if env_seed != "":
		model = WeatherModel.new(int(env_seed))
	else:
		model = WeatherModel.new(int(Time.get_unix_time_from_system()) % 100000)

func _day_index() -> int:
	return Game.day - 1

func current() -> Dictionary:
	return model.conditions_at(_day_index(), Game.hour())

func today() -> Dictionary:
	return model.day(_day_index())

## Forecast the player sees right now: tonight's frost odds + tomorrow's sky.
func forecast() -> Dictionary:
	return model.forecast_for(_day_index())

func today_label() -> String:
	return Qualitative.weather_pattern_label(today()["pattern"])

func forecast_label() -> String:
	return Qualitative.forecast_line(forecast())

func frost_warning_active() -> bool:
	return forecast()["frost_chance"] >= 0.3

## True while there is actual frost in the air right now.
func frost_now() -> bool:
	return current()["temp"] <= 0.0

## Visual frost intensity 0..1: full while subzero, then a rime that lingers
## and melts off over the morning hours so the player wakes to a white farm.
func frost_visual() -> float:
	var cond := current()
	if cond["temp"] <= 0.5:
		return clampf((1.5 - cond["temp"]) / 3.0, 0.3, 1.0)
	# look back a few hours for the last freeze
	var day_i := _day_index()
	var h := Game.hour()
	for back: float in [1.0, 2.0, 3.0, 4.0]:
		var bh: float = h - back
		var bd := day_i
		if bh < 0.0:
			bh += 24.0
			bd -= 1
		if bd < 0:
			break
		if model.conditions_at(bd, bh)["temp"] <= 0.0:
			return clampf(1.0 - back / 4.5, 0.0, 1.0) * 0.8
	return 0.0
