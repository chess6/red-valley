extends Node
## In-scene integration test: loads the real world and drives the actual
## player/Sarah/plot nodes through the signature frost scenario.
## Runs as a scene so autoloads exist:
##   godot --headless --path . res://tests/integration.tscn

var failures := 0
var checks := 0
var world: Node3D
var player: Player
var game: Node
var farm: Node
var weather: Node

func check(cond: bool, label: String) -> void:
	checks += 1
	if cond:
		print("  ok   %s" % label)
	else:
		failures += 1
		print("  FAIL %s" % label)

func _ready() -> void:
	# Day 0 is always gentle, so pick a seed whose SECOND night frosts and
	# fast-forward the calendar to that day.
	var seed_found := -1
	for s in 500:
		var m := WeatherModel.new(s)
		m.ensure_generated(2)
		if m.day(1)["t_night"] <= -2.0 and m.forecast_for(1)["frost_chance"] >= 0.3:
			seed_found = s
			break
	print("using frost seed: %d" % seed_found)
	game = get_node("/root/Game")
	farm = get_node("/root/Farm")
	weather = get_node("/root/Weather")
	weather.model = WeatherModel.new(seed_found)
	game.day = 2   # day index 1: the frosty night is tonight
	world = (load("res://scenes/world.tscn") as PackedScene).instantiate()
	get_tree().root.add_child.call_deferred(world)
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().process_frame
	player = get_tree().get_first_node_in_group("player")
	await run_scenario()
	print("")
	if failures == 0:
		print("INTEGRATION PASSED (%d checks)" % checks)
	else:
		print("%d INTEGRATION FAILURES of %d" % [failures, checks])
	get_tree().quit(1 if failures > 0 else 0)

func plots_by(owner_id: String, crop: String = "") -> Array:
	var out: Array = []
	for p in farm.plots_of(owner_id):
		if crop == "" or p.sim.crop_id == crop:
			out.append(p)
	return out

## Point the camera rig so its forward ray passes through `point`. The
## spring-arm camera sits opposite the rig's forward direction at a fixed
## distance from the rig's (fixed) pivot, so it looks straight through the
## pivot toward wherever the pivot-to-point direction points -- no iteration
## needed, this is exact regardless of spring length.
func aim_at(point: Vector3) -> void:
	var rig_origin: Vector3 = player.global_position + Vector3(0, 1.55, 0)
	var dir := (point - rig_origin).normalized()
	var euler := Basis.looking_at(dir, Vector3.UP).get_euler()
	player._cam_pitch = clampf(euler.x, -1.1, 0.25)
	player._cam_yaw = euler.y

func teleport_to(plot: Node3D) -> void:
	player.global_position = plot.global_position + Vector3(-1.2, 0.1, 0)
	for i in 2:
		await get_tree().physics_frame
	aim_at(plot.global_position + Vector3(0, 0.45, 0))
	for i in 6:
		await get_tree().physics_frame

func use_tool_on(plot: Node3D, tool_id: String) -> void:
	await teleport_to(plot)
	for i in Player.TOOLS.size():
		if Player.TOOLS[i]["id"] == tool_id:
			player.tool_index = i
	check(player.target_plot() == plot, "targeting the intended plot (%s)" % tool_id)
	player._use_tool()

func run_scenario() -> void:
	check(player != null, "player spawned")
	check(farm.plots.size() == 26, "26 plots registered (found %d)" % farm.plots.size())
	var sarah = get_tree().get_first_node_in_group("sarah")
	check(sarah != null, "Sarah spawned")
	check(weather.forecast()["frost_chance"] >= 0.3, "frost warning active on day 1")

	print("\n== actions cost time and change soil")
	var tom_plots := plots_by("player", "tomato")
	var t0: float = game.minutes
	var target: Node3D = tom_plots[0]
	var m0: float = target.sim.moisture
	await use_tool_on(target, "water")
	check(target.sim.moisture > m0 + 0.15, "watering raised moisture")
	check(game.minutes > t0 + 5.0, "watering consumed clock time")

	print("\n== planting consumes seeds")
	var empty: Array = plots_by("player").filter(func(p): return p.sim.crop_id == "")
	var seeds0: int = game.inventory["seed_potato"]
	player.seed_index = 2   # potato
	await use_tool_on(empty[0], "seeds")
	check(empty[0].sim.crop_id == "potato", "potato planted")
	check(game.inventory["seed_potato"] == seeds0 - 1, "seed consumed")

	print("\n== covering one tomato by hand")
	await use_tool_on(tom_plots[0], "cover")
	check(tom_plots[0].sim.covered, "cover applied")

	print("\n== earning reciprocity by helping Sarah")
	var her_dry: Array = plots_by("sarah")
	var r0: float = sarah.reciprocity
	for p in her_dry:
		if p.sim.has_crop():
			p.sim.moisture = 0.15   # she clearly needs the help
	for p in her_dry.slice(0, 4):
		await use_tool_on(p, "water")
	check(sarah.reciprocity > r0 + 2.0, "reciprocity earned (%.1f -> %.1f)" % [r0, sarah.reciprocity])

	print("\n== asking Sarah to cover the rest before the frost")
	game.minutes = 17.5 * 60.0   # evening
	var uncovered_before := plots_by("player").filter(
		func(p): return p.sim.has_crop() and not p.sim.covered and p.sim.crop()["frost_threshold_c"] > -3.0)
	var line: String = sarah.request_help("cover")
	print("  sarah: %s" % line)
	check(sarah.is_busy_helping(), "Sarah accepted and has a task queue")
	# let her physically walk and work (up to ~60s simulated)
	var deadline := 7200
	while sarah.is_busy_helping() and deadline > 0:
		await get_tree().physics_frame
		deadline -= 1
	var covered_by_sarah := 0
	for p in uncovered_before:
		if p.sim.covered:
			covered_by_sarah += 1
	check(covered_by_sarah >= 2, "Sarah physically covered %d plots" % covered_by_sarah)

	print("\n== the frost night resolves through the simulation")
	# leave one tender crop uncovered on purpose
	var uncovered_victim: Node3D = null
	for p in plots_by("player", "cabbage"):
		if not p.sim.covered:
			uncovered_victim = p
			break
	var victim_tom: Node3D = null
	for p in plots_by("player", "tomato"):
		if not p.sim.covered:
			victim_tom = p
			break
	if victim_tom == null:
		# all tomatoes got covered; uncover one to observe the contrast
		victim_tom = plots_by("player", "tomato")[0]
		victim_tom.sim.set_cover(false)
	var covered_tom: Node3D = null
	for p in plots_by("player", "tomato"):
		if p.sim.covered:
			covered_tom = p
			break
	game.sleep_until_morning()
	check(game.day == 3, "woke on day 3")
	print("  overnight low was %.1fC" % weather.model.day(1)["t_night"])
	check(victim_tom.sim.dead or victim_tom.sim.health < 0.5,
		"uncovered tomato badly frost-hurt (dead=%s health=%.2f)" % [victim_tom.sim.dead, victim_tom.sim.health])
	if covered_tom:
		check(not covered_tom.sim.dead and covered_tom.sim.health > 0.6,
			"covered tomato came through (health %.2f)" % covered_tom.sim.health)
	if uncovered_victim:
		check(not uncovered_victim.sim.dead and uncovered_victim.sim.health > 0.7,
			"uncovered cabbage shrugged it off (health %.2f)" % uncovered_victim.sim.health)

	print("\n== harvesting pays")
	var wheat: Array = plots_by("sarah", "wheat")
	# force-mature one of the player's plots for the harvest path instead
	var any_crop: Node3D = plots_by("player", "cabbage")[0]
	any_crop.sim.growth = 1.0
	any_crop.sim.set_cover(false)
	var coins0: int = game.coins
	await use_tool_on(any_crop, "hand")
	check(game.coins > coins0, "harvest earned coins (%d -> %d)" % [coins0, game.coins])
	check(any_crop.sim.crop_id == "", "plot cleared after harvest")

	print("\n== salvaging a grown-but-unripe crop costs a confirming second press")
	var growing: Node3D = plots_by("player", "wheat")[0]
	growing.sim.growth = 0.7
	growing.sim.dead = false
	growing.sim.set_cover(false)   # Sarah may have covered it earlier
	var coins1: int = game.coins
	await use_tool_on(growing, "hand")
	check(game.coins == coins1, "first press only arms the salvage, no coins yet")
	check(growing.sim.crop_id != "", "plot untouched after first press")
	player._use_tool()   # second press, immediately -- still aimed at the same plot
	check(game.coins > coins1, "second press confirms the early harvest and pays out")
	check(growing.sim.crop_id == "", "plot cleared after confirmed salvage")

	print("\n== shop transaction")
	var covers0: int = game.inventory["cover"]
	game.coins = 100
	check(game.try_buy("cover"), "bought a row cover")
	check(game.inventory["cover"] == covers0 + 1, "cover added to inventory")
