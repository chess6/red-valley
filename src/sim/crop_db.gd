class_name CropDB
extends RefCounted
## Data-driven crop definitions. All crops respond to the same generic model
## (moisture, temperature, fertility, frost) -- no special-cased pairings.
##
## Fields:
##   days_to_mature: in-game days under ideal conditions
##   moisture_lo/hi: comfort band for growth (0..1 soil moisture)
##   wilt_point:     below this the plant visibly wilts and takes drought stress
##   drought_rate:   health loss per hour per unit of moisture deficit
##   waterlog_tol:   0..1, higher = tolerates saturated soil longer
##   frost_threshold_c: air temp (C) at/below which frost damage starts
##   heat_threshold_c:  air temp (C) above which heat stress starts (bolting etc.)
##   heat_rate:      health loss per hour per degree above heat threshold
##   fert_demand:    fertility consumed over a full growth cycle
##   fert_hunger:    growth penalty weight when soil fertility is low
##   base_yield:     coins at harvest for a perfectly healthy crop
##   seed_cost:      coins per seed

const CROPS := {
	"tomato": {
		"label": "Tomato",
		"days_to_mature": 6.0,
		"moisture_lo": 0.35, "moisture_hi": 0.70,
		"wilt_point": 0.22,
		"drought_rate": 0.055,
		"waterlog_tol": 0.45,
		"frost_threshold_c": 1.0,
		"heat_threshold_c": 34.0,
		"heat_rate": 0.010,
		"fert_demand": 0.16,
		"fert_hunger": 0.8,
		"base_yield": 46,
		"seed_cost": 6,
		"blurb": "Loves warmth. Thirsty. Killed outright by frost.",
	},
	"cabbage": {
		"label": "Cabbage",
		"days_to_mature": 8.0,
		"moisture_lo": 0.45, "moisture_hi": 0.82,
		"wilt_point": 0.30,
		"drought_rate": 0.075,
		"waterlog_tol": 0.75,
		"frost_threshold_c": -4.0,
		"heat_threshold_c": 28.0,
		"heat_rate": 0.012,
		"fert_demand": 0.20,
		"fert_hunger": 1.0,
		"base_yield": 58,
		"seed_cost": 8,
		"blurb": "Hardy against cold, hates heat and thirst. Hungry feeder.",
	},
	"potato": {
		"label": "Potato",
		"days_to_mature": 7.0,
		"moisture_lo": 0.30, "moisture_hi": 0.62,
		"wilt_point": 0.18,
		"drought_rate": 0.035,
		"waterlog_tol": 0.25,
		"frost_threshold_c": 0.0,
		"heat_threshold_c": 33.0,
		"heat_rate": 0.008,
		"fert_demand": 0.12,
		"fert_hunger": 0.6,
		"base_yield": 40,
		"seed_cost": 5,
		"blurb": "Undemanding, but rots fast in soaked ground.",
	},
	"wheat": {
		"label": "Wheat",
		"days_to_mature": 5.0,
		"moisture_lo": 0.22, "moisture_hi": 0.58,
		"wilt_point": 0.12,
		"drought_rate": 0.018,
		"waterlog_tol": 0.50,
		"frost_threshold_c": -2.0,
		"heat_threshold_c": 36.0,
		"heat_rate": 0.006,
		"fert_demand": 0.08,
		"fert_hunger": 0.4,
		"base_yield": 24,
		"seed_cost": 3,
		"blurb": "Tough and quick, thrives on little. Modest payoff.",
	},
}

static func get_crop(id: String) -> Dictionary:
	return CROPS.get(id, {})

static func ids() -> Array:
	return CROPS.keys()
