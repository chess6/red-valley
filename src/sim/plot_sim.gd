class_name PlotSim
extends RefCounted
## Simulation state for a single field plot: soil water/fertility dynamics and
## the generic crop response model. Pure logic -- no scene nodes -- so it can
## be unit-tested headless and reused for Sarah's farm.

enum Soil { SANDY, LOAM, CLAY }

const SOIL_PARAMS := {
	Soil.SANDY: {
		"label": "sandy",
		"field_capacity": 0.55,   # moisture it can hold against gravity
		"infiltration": 1.0,      # fraction of rain that soaks in
		"drain_coeff": 0.45,      # per-hour drain of excess above capacity
		"percolation": 0.010,     # slow constant loss below capacity, per hour
		"evap_factor": 1.5,       # surface drying speed multiplier
		"base_fertility": 0.35,
	},
	Soil.LOAM: {
		"label": "loam",
		"field_capacity": 0.78,
		"infiltration": 0.85,
		"drain_coeff": 0.18,
		"percolation": 0.004,
		"evap_factor": 0.85,
		"base_fertility": 0.70,
	},
	Soil.CLAY: {
		"label": "clay",
		"field_capacity": 0.95,
		"infiltration": 0.55,
		"drain_coeff": 0.03,
		"percolation": 0.002,
		"evap_factor": 0.6,
		"base_fertility": 0.55,
	},
}

const WATERLOG_POINT := 0.88      # sustained moisture above this stresses roots
const BASE_EVAP := 0.014          # moisture units per hour at reference conditions
const COVER_FROST_BONUS := 5.0    # degrees C of protection from a row cover
const COVER_SUN_PENALTY := 0.55   # growth multiplier while covered
const MULCH_EVAP_CUT := 0.62      # fraction of evaporation prevented at full mulch

var soil: int = Soil.LOAM
var moisture: float = 0.45
var fertility: float = 0.5
var mulch: float = 0.0            # 0..1, decays daily
var covered: bool = false

var crop_id: String = ""          # "" = empty plot
var growth: float = 0.0           # 0..1
var health: float = 1.0
var dead: bool = false
var frostbitten: float = 0.0      # cosmetic memory of frost damage, 0..1
var _health_integral: float = 0.0 # for yield quality
var _growth_time: float = 0.0

func _init(soil_type: int = Soil.LOAM) -> void:
	soil = soil_type
	fertility = SOIL_PARAMS[soil]["base_fertility"]
	moisture = SOIL_PARAMS[soil]["field_capacity"] * 0.6

func soil_params() -> Dictionary:
	return SOIL_PARAMS[soil]

func crop() -> Dictionary:
	return CropDB.get_crop(crop_id) if crop_id != "" else {}

func has_crop() -> bool:
	return crop_id != "" and not dead

func mature() -> bool:
	return has_crop() and growth >= 1.0

# ------------------------------------------------------------------ actions

func plant(id: String) -> bool:
	if crop_id != "" and not dead:
		return false
	crop_id = id
	growth = 0.0
	health = 1.0
	dead = false
	frostbitten = 0.0
	_health_integral = 0.0
	_growth_time = 0.0
	return true

func clear_plot() -> void:
	crop_id = ""
	dead = false
	growth = 0.0
	health = 1.0
	frostbitten = 0.0

func water() -> void:
	moisture = minf(moisture + 0.28, 1.0)

func apply_compost() -> void:
	fertility = minf(fertility + 0.15, 1.0)

func apply_manure() -> String:
	## Strong, but scorches tender young plants -- a judgment call.
	fertility = minf(fertility + 0.35, 1.0)
	if has_crop() and growth < 0.5:
		health = maxf(health - 0.18, 0.05)
		return "burned"
	return "ok"

func apply_mulch() -> void:
	mulch = 1.0

func set_cover(on: bool) -> void:
	covered = on

## Harvest a mature crop. Returns coins earned (0 if nothing to harvest).
func harvest() -> int:
	if not mature():
		return 0
	var c := crop()
	var avg_health := _health_integral / maxf(_growth_time, 0.001)
	var quality := clampf(0.25 + 0.75 * avg_health, 0.0, 1.0)
	var coins := int(round(float(c["base_yield"]) * quality))
	clear_plot()
	return coins

## Once-per-day housekeeping (called at dawn).
func end_of_day() -> void:
	mulch = maxf(mulch - 0.12, 0.0)

# ------------------------------------------------------------------ sim tick

## Advance dt_hours under environment env = {temp, raining, rain_rate, sun}.
func tick(dt_hours: float, env: Dictionary) -> void:
	_tick_soil(dt_hours, env)
	if has_crop():
		_tick_crop(dt_hours, env)

func _tick_soil(dt: float, env: Dictionary) -> void:
	var p := soil_params()
	# Rain infiltration (a cover sheds most rain off the plot).
	if env.get("raining", false):
		var infil: float = p["infiltration"]
		if covered:
			infil *= 0.25
		moisture += env["rain_rate"] * infil * dt
	# Evaporation, driven by heat and sun, damped by mulch/cover and clay.
	var temp_factor: float = clampf((env["temp"] - 5.0) / 20.0, 0.15, 2.2)
	var sun_factor: float = 0.25 + 0.75 * env.get("sun", 0.0)
	var canopy := 1.0 + (0.5 * growth if has_crop() else 0.0)
	var evap: float = BASE_EVAP * temp_factor * sun_factor * p["evap_factor"] * canopy
	evap *= 1.0 - MULCH_EVAP_CUT * mulch
	if covered:
		evap *= 0.55
	moisture -= evap * dt
	# Drainage of excess above field capacity + slow percolation below it.
	var cap: float = p["field_capacity"]
	if moisture > cap:
		moisture -= (moisture - cap) * p["drain_coeff"] * dt
	moisture -= p["percolation"] * dt
	moisture = clampf(moisture, 0.02, 1.0)
	# Fertility creeps back toward the soil's natural baseline.
	var base: float = p["base_fertility"]
	fertility = move_toward(fertility, base, 0.01 / 24.0 * dt)

func _tick_crop(dt: float, env: Dictionary) -> void:
	var c := crop()
	var temp: float = env["temp"]

	# --- stress ---
	var stress := 0.0
	if moisture < c["wilt_point"]:
		stress += c["drought_rate"] * (c["wilt_point"] - moisture) / maxf(c["wilt_point"], 0.01) * 2.0
	if moisture > WATERLOG_POINT:
		var wl_severity: float = (moisture - WATERLOG_POINT) / (1.0 - WATERLOG_POINT)
		var wl_frailty: float = (1.0 - c["waterlog_tol"]) * (1.0 - c["waterlog_tol"])
		stress += 0.12 * wl_severity * wl_frailty
	if temp > c["heat_threshold_c"]:
		# Well-watered plants cope with heat far better (turgor + cooling).
		var band := clampf((moisture - c["moisture_lo"]) / maxf(c["moisture_hi"] - c["moisture_lo"], 0.01), 0.0, 1.0)
		stress += c["heat_rate"] * (temp - c["heat_threshold_c"]) * (1.0 - 0.5 * band)
	# Frost: continuous while air temp sits below the crop's threshold;
	# quadratic in severity so a borderline night nips, a hard one kills.
	var effective_temp := temp + (COVER_FROST_BONUS if covered else 0.0)
	if effective_temp < c["frost_threshold_c"]:
		var frost_severity: float = c["frost_threshold_c"] - effective_temp
		stress += 0.10 * frost_severity * frost_severity
		frostbitten = clampf(frostbitten + 0.5 * dt, 0.0, 1.0)

	health -= stress * dt
	# Slow recovery when comfortable.
	if stress == 0.0 and moisture >= c["moisture_lo"] and moisture <= c["moisture_hi"]:
		health += 0.004 * dt
	health = clampf(health, 0.0, 1.0)
	if health <= 0.0:
		dead = true
		return

	# --- growth ---
	var f_moist := _comfort(moisture, c["moisture_lo"], c["moisture_hi"], 0.15)
	var f_temp := clampf((temp - 4.0) / 14.0, 0.0, 1.0)  # cold halts growth
	if temp > c["heat_threshold_c"]:
		f_temp *= 0.5
	var f_fert: float = clampf(lerpf(1.0, fertility * 1.4, c["fert_hunger"]), 0.15, 1.0)
	var f_sun: float = 0.3 + 0.7 * env.get("sun", 0.0)
	if covered:
		f_sun *= COVER_SUN_PENALTY
	# ~14 effective growing hours per ideal day.
	var rate: float = 1.0 / (c["days_to_mature"] * 14.0)
	var growth_step: float = rate * f_moist * f_temp * f_fert * f_sun * (0.4 + 0.6 * health) * dt
	if growth < 1.0 and growth_step > 0.0:
		growth = minf(growth + growth_step, 1.0)
		fertility = maxf(fertility - c["fert_demand"] * growth_step, 0.02)
	_health_integral += health * dt
	_growth_time += dt
	frostbitten = maxf(frostbitten - 0.02 * dt, 0.0)

## 1.0 inside [lo, hi], falling linearly to 0 over `margin` outside the band.
func _comfort(x: float, lo: float, hi: float, margin: float) -> float:
	if x >= lo and x <= hi:
		return 1.0
	var d := (lo - x) if x < lo else (x - hi)
	return clampf(1.0 - d / margin, 0.0, 1.0)

## Visible wilt 0..1 (drives drooping/yellowing visuals + inspection text).
func wilt_level() -> float:
	if not has_crop():
		return 0.0
	var c := crop()
	var w := 0.0
	if moisture < c["moisture_lo"]:
		w = clampf((c["moisture_lo"] - moisture) / maxf(c["moisture_lo"] - c["wilt_point"] * 0.5, 0.05), 0.0, 1.0)
	w = maxf(w, 1.0 - health)
	return clampf(w, 0.0, 1.0)
