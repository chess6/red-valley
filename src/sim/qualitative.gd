class_name Qualitative
extends RefCounted
## Translates raw simulation numbers into the observations a farmer would
## actually make. The normal game never shows the numbers themselves.

static func soil_feel(p: PlotSim) -> String:
	var texture := ""
	match p.soil:
		PlotSim.Soil.SANDY: texture = "The soil is pale and gritty; water runs straight through it."
		PlotSim.Soil.LOAM: texture = "Dark, crumbly soil. It holds together when you squeeze it."
		PlotSim.Soil.CLAY: texture = "Heavy reddish clay. Dense, and slow to let water past."
	var m := p.moisture
	var cap: float = p.soil_params()["field_capacity"]
	var wet := ""
	if m > PlotSim.WATERLOG_POINT:
		wet = "It's waterlogged -- water pools when you press your boot in."
	elif m > cap * 0.95:
		wet = "It's soaked through."
	elif m > cap * 0.7:
		wet = "It feels pleasantly damp under the surface."
	elif m > cap * 0.45:
		wet = "It's starting to dry out."
	elif m > cap * 0.28:
		wet = "It's dry a finger's depth down."
	else:
		wet = "It's bone dry and dusty."
	var fert := ""
	if p.fertility > 0.75:
		fert = "Rich, well-fed ground."
	elif p.fertility > 0.5:
		fert = "Decent fertility."
	elif p.fertility > 0.3:
		fert = "The ground seems a little tired."
	else:
		fert = "Thin, hungry soil."
	var extras := ""
	if p.mulch > 0.4:
		extras += " A layer of mulch is keeping the surface shaded."
	elif p.mulch > 0.0:
		extras += " The mulch layer is wearing thin."
	if p.covered:
		extras += " A row cover is pinned over this plot."
	return "%s %s %s%s" % [texture, wet, fert, extras]

static func crop_report(p: PlotSim) -> String:
	if p.crop_id == "":
		return "Nothing planted here."
	var c := p.crop()
	var name: String = c["label"]
	if p.dead:
		if p.frostbitten > 0.3:
			return "The %s is dead -- blackened and limp from frost." % name.to_lower()
		return "The %s is dead. Nothing to save here." % name.to_lower()
	var lines: PackedStringArray = []
	# growth stage
	if p.growth >= 1.0:
		lines.append("The %s is ready to harvest." % name.to_lower())
	elif p.growth > 0.75:
		lines.append("The %s is nearly ready -- give it a little longer." % name.to_lower())
	elif p.growth > 0.45:
		lines.append("The %s is well established and filling out." % name.to_lower())
	elif p.growth > 0.15:
		lines.append("The young %s has taken root." % name.to_lower())
	else:
		lines.append("The %s seedlings are just emerging." % name.to_lower())
	# frost memory
	if p.frostbitten > 0.5:
		lines.append("The leaves are scorched dark where frost caught them.")
	elif p.frostbitten > 0.15:
		lines.append("Some leaf edges look frost-nipped.")
	# water state
	var wilt := p.wilt_level()
	if p.moisture > PlotSim.WATERLOG_POINT:
		lines.append("The roots are sitting in water. It can't stay like this for long.")
	elif wilt > 0.65:
		lines.append("The leaves are badly wilted and curling.")
	elif wilt > 0.3:
		lines.append("Leaves look slightly wilted. Needs more water.")
	elif p.moisture > c["moisture_hi"]:
		lines.append("The ground is wetter than it likes.")
	# overall vigour
	if p.health < 0.35:
		lines.append("It's in a bad way -- it may not pull through.")
	elif p.health < 0.65:
		lines.append("It's struggling, but could still recover.")
	elif wilt <= 0.3 and p.moisture <= PlotSim.WATERLOG_POINT:
		if p.fertility < 0.3 and c["fert_hunger"] > 0.6:
			lines.append("Growth seems slow -- the plant looks pale and underfed.")
		else:
			lines.append("It looks healthy.")
	return " ".join(lines)

## One short line for the aiming reticle (concept art style).
static func short_status(p: PlotSim) -> String:
	if p.crop_id == "":
		var m := p.moisture
		var cap: float = p.soil_params()["field_capacity"]
		if m > PlotSim.WATERLOG_POINT:
			return "Empty plot -- waterlogged"
		elif m < cap * 0.3:
			return "Empty plot -- dry %s soil" % p.soil_params()["label"]
		return "Empty plot -- %s soil" % p.soil_params()["label"]
	var c := p.crop()
	if p.dead:
		return "%s -- dead" % c["label"]
	if p.growth >= 1.0:
		return "%s -- ready to harvest!" % c["label"]
	var wilt := p.wilt_level()
	if p.moisture > PlotSim.WATERLOG_POINT:
		return "%s -- roots sitting in water" % c["label"]
	if wilt > 0.65:
		return "%s -- badly wilted" % c["label"]
	if wilt > 0.3:
		return "%s -- slightly wilted" % c["label"]
	if p.health < 0.6:
		return "%s -- struggling" % c["label"]
	return "%s -- looks healthy" % c["label"]

static func weather_pattern_label(pattern: int) -> String:
	match pattern:
		WeatherModel.CLEAR: return "Clear"
		WeatherModel.HOT_DRY: return "Hot & dry"
		WeatherModel.OVERCAST: return "Overcast"
		WeatherModel.RAIN: return "Rain"
		WeatherModel.HEAVY_RAIN: return "Heavy rain"
		WeatherModel.COLD_SNAP: return "Cold"
	return "Clear"

static func forecast_line(f: Dictionary) -> String:
	var parts: PackedStringArray = []
	parts.append(weather_pattern_label(f["pattern"]))
	if f["frost_chance"] >= 0.15:
		parts.append("Frost (%d%%)" % int(round(f["frost_chance"] * 100)))
	elif f["rain_chance"] >= 0.5:
		parts.append("Rain likely")
	elif f["rain_chance"] >= 0.2:
		parts.append("Maybe rain")
	return ", ".join(parts)
