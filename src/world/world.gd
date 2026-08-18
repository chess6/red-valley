extends Node3D
## Builds the whole valley procedurally from the generated GLB assets and
## drives day/night lighting + weather visuals from the simulation clock.

const FENCE_LEN := 2.0

var sun: DirectionalLight3D
var env: Environment
var sky_mat: ProceduralSkyMaterial
var rain: GPUParticles3D
var windmill_blades: Node3D
var player: Node3D
var sarah: Node3D
var _wetness := 0.0
var _refresh_timer := 0.0

func _ready() -> void:
	_build_lighting()
	_build_ground()
	_build_props()
	_build_fields()
	_build_rain()
	_spawn_actors()
	var hud_scene := load("res://src/ui/hud.gd")
	var hud = hud_scene.new()
	add_child(hud)
	_maybe_screenshot()

## Dev harness: RV_SHOT_FILE=/tmp/x.png [RV_SHOT_HOUR=18.5] [RV_SHOT_POS=x,z]
## [RV_SHOT_YAW=2.4] [RV_SHOT_PITCH=-0.3] -> settle, snap, quit.
func _maybe_screenshot() -> void:
	var file := OS.get_environment("RV_SHOT_FILE")
	if file == "":
		return
	var day_s := OS.get_environment("RV_SHOT_DAY")
	if day_s != "":
		Game.day = int(day_s)
	var hour_s := OS.get_environment("RV_SHOT_HOUR")
	if hour_s != "":
		Game.minutes = float(hour_s) * 60.0
	var pos_s := OS.get_environment("RV_SHOT_POS")
	await get_tree().process_frame
	if pos_s != "":
		var parts := pos_s.split(",")
		player.position = Vector3(float(parts[0]), 0.1, float(parts[1]))
	var yaw_s := OS.get_environment("RV_SHOT_YAW")
	if yaw_s != "":
		player._cam_yaw = float(yaw_s)
	var pitch_s := OS.get_environment("RV_SHOT_PITCH")
	if pitch_s != "":
		player._cam_pitch = float(pitch_s)
	for i in 110:
		await get_tree().process_frame
	var action := OS.get_environment("RV_SHOT_ACTION")
	if action != "":
		match action:
			"inspect":
				player._inspect()
			"dialogue":
				get_tree().get_first_node_in_group("sarah").talk_to()
			"shop":
				get_tree().call_group("hud", "open_shop")
			"debug":
				var chips := get_tree().get_nodes_in_group("hud")
				for c in chips:
					c.debug_label.get_parent().visible = true
			"states":
				# showcase every visual crop/soil state on the loam field
				var loam := Farm.plots_of("player").filter(func(p): return p.sim.soil == PlotSim.Soil.LOAM)
				loam[0].sim.set_cover(true)                      # covered tomato
				loam[1].sim.health = 0.0; loam[1].sim.dead = true  # frost-killed
				loam[1].sim.frostbitten = 1.0
				loam[2].sim.growth = 1.0                          # mature cabbage
				loam[3].sim.moisture = 0.15                       # wilting cabbage
				loam[4].sim.plant("tomato"); loam[4].sim.growth = 1.0  # ripe tomatoes
				loam[5].sim.apply_mulch()                         # mulched plot
				loam[6].sim.plant("wheat"); loam[6].sim.growth = 1.0   # golden wheat
				loam[7].sim.moisture = 1.0                        # waterlogged
				for pl in loam:
					pl.refresh_visuals()
		for i in 15:
			await get_tree().process_frame
	var img := get_viewport().get_texture().get_image()
	img.save_png(file)
	print("screenshot saved: ", file)
	get_tree().quit()

# ------------------------------------------------------------ construction

func _glb(path: String, pos: Vector3, rot_y := 0.0, scale_f := 1.0) -> Node3D:
	var inst: Node3D = load("res://assets/models/" + path + ".glb").instantiate()
	inst.position = pos
	inst.rotation.y = rot_y
	if scale_f != 1.0:
		inst.scale = Vector3.ONE * scale_f
	add_child(inst)
	return inst

## Static collider so the player can't walk through a building.
func _blocker(pos: Vector3, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	body.position = pos + Vector3(0, size.y * 0.5, 0)
	body.add_child(cs)
	add_child(body)

## Invisible interactable (door, crate...) the player can aim at + press E.
func _interactable(kind: String, pos: Vector3, size: Vector3, prompt: String) -> void:
	var body := StaticBody3D.new()
	body.collision_layer = 2
	body.collision_mask = 0
	var cs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = size
	cs.shape = box
	body.position = pos + Vector3(0, size.y * 0.5, 0)
	body.add_child(cs)
	body.set_meta("interact", kind)
	body.set_meta("prompt", prompt)
	add_child(body)

func _build_lighting() -> void:
	sun = DirectionalLight3D.new()
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 120.0
	add_child(sun)
	env = Environment.new()
	sky_mat = ProceduralSkyMaterial.new()
	sky_mat.sky_horizon_color = Color(0.75, 0.78, 0.75)
	sky_mat.ground_bottom_color = Color(0.2, 0.24, 0.16)
	sky_mat.ground_horizon_color = Color(0.65, 0.68, 0.6)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	env.fog_enabled = true
	env.fog_light_color = Color(0.75, 0.8, 0.82)
	env.fog_density = 0.001
	env.fog_sky_affect = 0.2
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)

func _build_ground() -> void:
	# grass plane
	var ground := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(500, 500)
	ground.mesh = plane
	var gmat := ShaderMaterial.new()
	gmat.shader = load("res://assets/grass.gdshader")
	ground.material_override = gmat
	add_child(ground)
	# floor collision
	var body := StaticBody3D.new()
	body.collision_layer = 1
	var cs := CollisionShape3D.new()
	var shape := WorldBoundaryShape3D.new()
	cs.shape = shape
	body.add_child(cs)
	add_child(body)
	# surrounding hills (visual only)
	_glb("hills", Vector3.ZERO)
	# dirt paths
	_path_strip(Vector3(-13, 0, -14), Vector3(-13, 0, 0))
	_path_strip(Vector3(-13, 0, -2), Vector3(14, 0, -2))
	_path_strip(Vector3(14, 0, -2), Vector3(44, 0, 0))

func _path_strip(from: Vector3, to: Vector3) -> void:
	var mid := (from + to) * 0.5
	var length := from.distance_to(to)
	var strip := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(2.2, length + 2.2)
	strip.mesh = plane
	var m := StandardMaterial3D.new()
	m.albedo_color = Color(0.52, 0.4, 0.27)
	m.roughness = 1.0
	strip.material_override = m
	strip.position = mid + Vector3(0, 0.02, 0)
	strip.rotation.y = atan2(to.x - from.x, to.z - from.z)
	add_child(strip)

func _build_props() -> void:
	# player farm
	_glb("farmhouse", Vector3(-14, 0, -20))
	_blocker(Vector3(-14, 0, -20), Vector3(5.4, 3, 4.2))
	_interactable("sleep", Vector3(-13.1, 0, -17.6), Vector3(1.6, 2.2, 1.2), "Sleep until morning")
	_glb("shed", Vector3(-24, 0, -14), 0.3)
	_blocker(Vector3(-24, 0, -14), Vector3(2.8, 2, 2.4))
	_glb("crate", Vector3(-22.2, 0, -11.6), 0.5)
	_interactable("shop", Vector3(-22.2, 0, -11.6), Vector3(1.4, 1.2, 1.2), "Browse supplies")
	_glb("well", Vector3(-4, 0, -12))
	_blocker(Vector3(-4, 0, -12), Vector3(1.6, 1.4, 1.6))
	_glb("windmill_base", Vector3(18, 0, -24))
	_blocker(Vector3(18, 0, -24), Vector3(2, 6.5, 2))
	windmill_blades = _glb("windmill_blades", Vector3(18, 0.0, -24))
	windmill_blades.position += Vector3(0, 6.3, 0.75)
	# Sarah's farm
	_glb("sarah_house", Vector3(40, 0, -8))
	_blocker(Vector3(40, 0, -8), Vector3(4.4, 3, 3.6))
	_glb("fence", Vector3(33, 0, -10), PI / 2)
	_glb("fence", Vector3(33, 0, -8), PI / 2)
	# fences around player farm with an east gap toward Sarah
	_fence_run(Vector3(-27, 0, -25), Vector3(23, 0, -25))
	_fence_run(Vector3(-27, 0, 13), Vector3(23, 0, 13))
	_fence_run(Vector3(-27, 0, -25), Vector3(-27, 0, 13))
	_fence_run(Vector3(23, 0, -25), Vector3(23, 0, -6))
	_fence_run(Vector3(23, 0, 2), Vector3(23, 0, 13))
	# trees + rocks around the valley
	var rng := RandomNumberGenerator.new()
	rng.seed = 99
	for i in 26:
		var a := rng.randf_range(0, TAU)
		var d := rng.randf_range(38, 85)
		var pos := Vector3(cos(a) * d, 0, sin(a) * d)
		if pos.x > 28 and pos.x < 52 and pos.z > -16 and pos.z < 12:
			continue  # keep Sarah's yard clear
		_glb("tree1" if i % 2 == 0 else "tree2", pos, rng.randf_range(0, TAU), rng.randf_range(0.8, 1.5))
	for i in 8:
		var a2 := rng.randf_range(0, TAU)
		var d2 := rng.randf_range(30, 70)
		_glb("rock", Vector3(cos(a2) * d2, 0, sin(a2) * d2), rng.randf_range(0, TAU), rng.randf_range(0.7, 1.6))
	# a few trees inside view near the farm
	_glb("tree1", Vector3(-26, 0, 3), 1.0, 1.2)
	_glb("tree2", Vector3(20, 0, -16), 2.0, 1.1)

func _fence_run(from: Vector3, to: Vector3) -> void:
	var dir := to - from
	var count := int(dir.length() / FENCE_LEN)
	var step := dir.normalized() * FENCE_LEN
	var rot := atan2(dir.x, dir.z) + PI / 2
	for i in count:
		var pos := from + step * (i + 0.5)
		_glb("fence", pos, rot)
	# collision along the run
	var mid := (from + to) * 0.5
	var size := Vector3(maxf(absf(dir.x), 0.3), 1.0, maxf(absf(dir.z), 0.3))
	_blocker(mid, size)

func _build_fields() -> void:
	var sandy := _make_field(Vector3(-12, 0, 2), 3, 2, PlotSim.Soil.SANDY, "player")
	var loam := _make_field(Vector3(-1, 0, 6), 4, 2, PlotSim.Soil.LOAM, "player")
	_make_field(Vector3(11, 0, 2), 3, 2, PlotSim.Soil.CLAY, "player")
	var hers := _make_field(Vector3(38, 0, 4), 3, 2, PlotSim.Soil.LOAM, "sarah")
	# You took the farm over mid-season: some crops are already growing,
	# so the first frost warning is a real decision, not a tutorial.
	_start_crop(loam[0], "tomato", 0.62)
	_start_crop(loam[1], "tomato", 0.58)
	_start_crop(loam[2], "cabbage", 0.5)
	_start_crop(loam[3], "cabbage", 0.46)
	_start_crop(sandy[0], "wheat", 0.35)
	# Sarah's field looks lived-in too.
	_start_crop(hers[0], "potato", 0.55)
	_start_crop(hers[1], "potato", 0.5)
	_start_crop(hers[2], "cabbage", 0.4)
	_start_crop(hers[3], "wheat", 0.6)

func _start_crop(plot: Plot, crop_id: String, growth: float) -> void:
	plot.sim.plant(crop_id)
	plot.sim.growth = growth

func _make_field(center: Vector3, cols: int, rows: int, soil: int, owner_name: String) -> Array:
	var spacing := 2.3
	var made: Array = []
	for cx in cols:
		for cz in rows:
			var offset := Vector3(
				(cx - (cols - 1) * 0.5) * spacing, 0,
				(cz - (rows - 1) * 0.5) * spacing)
			var plot := Plot.make(soil, owner_name)
			plot.position = center + offset
			add_child(plot)
			made.append(plot)
	return made

func _build_rain() -> void:
	rain = GPUParticles3D.new()
	var pm := ParticleProcessMaterial.new()
	pm.direction = Vector3(0, -1, 0)
	pm.spread = 3.0
	pm.initial_velocity_min = 18.0
	pm.initial_velocity_max = 22.0
	pm.gravity = Vector3(0, -20, 0)
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = Vector3(20, 1, 20)
	rain.process_material = pm
	var drop := BoxMesh.new()
	drop.size = Vector3(0.02, 0.55, 0.02)
	var dm := StandardMaterial3D.new()
	dm.albedo_color = Color(0.75, 0.82, 0.95, 0.5)
	dm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	dm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	drop.material = dm
	rain.draw_pass_1 = drop
	rain.amount = 1600
	rain.lifetime = 1.4
	rain.visibility_aabb = AABB(Vector3(-30, -16, -30), Vector3(60, 20, 60))
	rain.emitting = false
	add_child(rain)

func _spawn_actors() -> void:
	player = load("res://src/player/player.gd").new()
	player.position = Vector3(-11, 0.1, -14)
	add_child(player)
	sarah = load("res://src/npc/sarah.gd").new()
	sarah.position = Vector3(41, 0.1, 0)
	add_child(sarah)

# ------------------------------------------------------------ per-frame

func _process(delta: float) -> void:
	var cond: Dictionary = Weather.current()
	_update_sun(cond)
	_update_weather_fx(cond, delta)
	_refresh_timer -= delta
	if _refresh_timer <= 0.0:
		_refresh_timer = 0.5
		for p in Farm.plots:
			p.refresh_visuals()

func _update_sun(cond: Dictionary) -> void:
	var h := Game.hour()
	var t := clampf((h - 6.0) / 14.0, 0.0, 1.0)     # 0 at 06:00, 1 at 20:00
	var elevation := sin(t * PI)
	var daylight := clampf(elevation * 1.4, 0.0, 1.0)
	if h < 6.0 or h > 20.0:
		daylight = 0.0
	var cloud: float = cond["cloud"]
	sun.rotation = Vector3(-maxf(elevation, 0.06) * PI * 0.45 - 0.1, lerpf(-2.2, 2.2, t) * 0.5, 0)
	sun.light_energy = daylight * (1.0 - 0.65 * cloud) + 0.03
	var warm := clampf(1.0 - elevation * 2.2, 0.0, 1.0)  # sunrise/sunset
	sun.light_color = Color(1.0, 1.0 - 0.25 * warm, 1.0 - 0.45 * warm)
	# sky palette through the day
	var night_top := Color(0.03, 0.05, 0.12)
	var night_hor := Color(0.08, 0.1, 0.18)
	var day_top := Color(0.3, 0.55, 0.85).lerp(Color(0.45, 0.5, 0.55), cloud)
	var day_hor := Color(0.75, 0.82, 0.85).lerp(Color(0.6, 0.62, 0.6), cloud)
	var dawn_top := Color(0.25, 0.3, 0.55)
	var dawn_hor := Color(0.95, 0.6, 0.35)
	var top: Color; var hor: Color
	if daylight <= 0.0:
		top = night_top; hor = night_hor
	elif daylight < 0.35:
		var k := daylight / 0.35
		top = night_top.lerp(dawn_top, k); hor = night_hor.lerp(dawn_hor, k)
	else:
		var k2 := (daylight - 0.35) / 0.65
		top = dawn_top.lerp(day_top, k2); hor = dawn_hor.lerp(day_hor, k2)
	sky_mat.sky_top_color = top
	sky_mat.sky_horizon_color = hor
	env.ambient_light_energy = maxf(daylight * (1.0 - 0.45 * cloud), 0.12)

func _update_weather_fx(cond: Dictionary, delta: float) -> void:
	var raining: bool = cond["raining"] or OS.get_environment("RV_FORCE_RAIN") != ""
	rain.emitting = raining
	if raining and player:
		rain.position = player.position + Vector3(0, 12, 0)
		rain.amount_ratio = clampf(cond["rain_rate"] / 0.25, 0.4, 1.0)
	_wetness = move_toward(_wetness, 1.0 if raining else 0.0, delta * (0.3 if raining else 0.02))
	RenderingServer.global_shader_parameter_set("wetness", _wetness)
	var frost: float = Weather.frost_visual()
	RenderingServer.global_shader_parameter_set("frost_amount", frost)
	env.fog_density = 0.001 + 0.004 * cond["cloud"] + 0.008 * frost
	if windmill_blades:
		var wind: float = 0.5 + (2.0 if raining else 0.0) + cond["cloud"]
		windmill_blades.rotation.z += wind * delta
