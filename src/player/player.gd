class_name Player
extends CharacterBody3D
## Third-person farmer: movement, orbit camera, aiming at plots/interactables,
## and the tool hotbar. Every field action costs in-game minutes.

const WALK_SPEED := 4.3
const RUN_SPEED := 7.0
const MOUSE_SENS := 0.0028
const AIM_RANGE := 9.0  # camera sits up to spring_length (5.2) behind the player
## Night blocks ALL field work except covering up (frost protection is the
## one thing you're allowed to scramble for after dark) and the always-free
## look-but-don't-touch actions (hand-tool inspect, harvesting what's already
## ripe, folding away a cover, clearing a dead plant).
const NIGHT_BLOCKED_TOOLS := ["water", "seeds", "compost", "manure", "mulch"]

const TOOLS := [
	{"id": "hand", "label": "Hand", "hint": "harvest / clear / uncover / salvage early (press twice)"},
	{"id": "water", "label": "Watering can", "hint": "water a plot"},
	{"id": "seeds", "label": "Seeds", "hint": "plant (press again to change crop)"},
	{"id": "compost", "label": "Compost", "hint": "gentle fertility"},
	{"id": "manure", "label": "Manure", "hint": "strong fertility, scorches seedlings"},
	{"id": "mulch", "label": "Mulch", "hint": "keeps moisture in"},
	{"id": "cover", "label": "Row cover", "hint": "frost protection"},
]
const SEED_CYCLE := ["tomato", "cabbage", "potato", "wheat"]

var tool_index := 0
var seed_index := 0
var current_target: Node3D = null      # StaticBody3D with meta
var _pending_harvest_plot: Plot = null # armed by a first early-harvest press
var _pending_harvest_timer := 0.0
var _cam_yaw := 0.0
var _cam_pitch := -0.35
var _rig: Node3D
var _spring: SpringArm3D
var _cam: Camera3D
var _visual: Node3D
var _bob_t := 0.0

func _ready() -> void:
	add_to_group("player")
	collision_layer = 1
	collision_mask = 1
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.7
	cs.shape = cap
	cs.position.y = 0.85
	add_child(cs)
	_visual = load("res://assets/models/farmer.glb").instantiate()
	add_child(_visual)
	_rig = Node3D.new()
	_rig.position.y = 1.55
	add_child(_rig)
	_spring = SpringArm3D.new()
	_spring.spring_length = 5.2
	_spring.collision_mask = 1
	_spring.margin = 0.3
	_rig.add_child(_spring)
	_cam = Camera3D.new()
	_cam.fov = 65
	_spring.add_child(_cam)
	_cam.current = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and Input.mouse_mode == Input.MOUSE_MODE_CAPTURED:
		_cam_yaw -= event.relative.x * MOUSE_SENS
		_cam_pitch = clampf(_cam_pitch - event.relative.y * MOUSE_SENS, -1.1, 0.25)
	if not Game.running:
		return
	for i in TOOLS.size():
		if event.is_action_pressed("slot_%d" % (i + 1)):
			if TOOLS[i]["id"] == "seeds" and tool_index == i:
				seed_index = (seed_index + 1) % SEED_CYCLE.size()
			tool_index = i
	if event.is_action_pressed("use_tool"):
		_use_tool()
	if event.is_action_pressed("interact"):
		_interact()
	if event.is_action_pressed("inspect"):
		_inspect()
	if event.is_action_pressed("wait_hour"):
		Game.wait_one_hour()
		Game.notify("You take a breather for an hour.")

func _physics_process(delta: float) -> void:
	_rig.rotation = Vector3(_cam_pitch, _cam_yaw, 0)
	if _pending_harvest_timer > 0.0:
		_pending_harvest_timer -= delta
		if _pending_harvest_timer <= 0.0:
			_pending_harvest_plot = null
	if not Game.running:
		return
	var input := Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var dir := (Basis(Vector3.UP, _cam_yaw) * Vector3(input.x, 0, input.y)).normalized()
	var speed := RUN_SPEED if Input.is_action_pressed("run") else WALK_SPEED
	velocity.x = dir.x * speed * minf(input.length() * 2.0, 1.0) if input != Vector2.ZERO else move_toward(velocity.x, 0, 30 * delta)
	velocity.z = dir.z * speed * minf(input.length() * 2.0, 1.0) if input != Vector2.ZERO else move_toward(velocity.z, 0, 30 * delta)
	if not is_on_floor():
		velocity.y -= 22.0 * delta
	else:
		velocity.y = 0.0
	move_and_slide()
	# face movement direction + walk bob
	var planar := Vector3(velocity.x, 0, velocity.z)
	if planar.length() > 0.5:
		var target_rot := atan2(planar.x, planar.z)
		_visual.rotation.y = lerp_angle(_visual.rotation.y, target_rot, 10.0 * delta)
		_bob_t += delta * planar.length() * 2.2
		_visual.position.y = absf(sin(_bob_t)) * 0.06
		_visual.rotation.z = sin(_bob_t) * 0.03
	else:
		_visual.position.y = move_toward(_visual.position.y, 0, delta)
		_visual.rotation.z = lerp_angle(_visual.rotation.z, 0, 8 * delta)
	_update_target()

## What the camera is actually looking at (layer 2), within reach.
func _update_target() -> void:
	var space := get_world_3d().direct_space_state
	var from := _cam.global_position
	var to := from + -_cam.global_transform.basis.z * AIM_RANGE
	var params := PhysicsRayQueryParameters3D.create(from, to)
	params.collision_mask = 2
	params.collide_with_areas = false
	var hit := space.intersect_ray(params)
	current_target = hit["collider"] if hit else null

func target_plot() -> Plot:
	if current_target and current_target.has_meta("plot"):
		return current_target.get_meta("plot")
	return null

func target_interact_kind() -> String:
	if current_target and current_target.has_meta("interact"):
		return current_target.get_meta("interact")
	return ""

# ------------------------------------------------------------------ actions

func _blocked_by_night(tool_id: String) -> bool:
	if tool_id not in NIGHT_BLOCKED_TOOLS:
		return false
	if Game.is_night() and Weather.current()["sun"] <= 0.0:
		Game.notify("Too dark for field work. Better get some sleep.")
		return true
	return false

func _use_tool() -> void:
	var plot := target_plot()
	if plot == null:
		return
	var sim: PlotSim = plot.sim
	var tool_id: String = TOOLS[tool_index]["id"]
	if _blocked_by_night(tool_id):
		return
	match tool_id:
		"hand":
			if sim.covered:
				sim.set_cover(false)
				Game.give_item("cover")
				Game.spend_action("uncover")
				Game.notify("You fold the row cover away.")
			elif sim.dead:
				sim.clear_plot()
				Game.spend_action("plant")
				Game.notify("You pull out the dead plant and clear the plot.")
			elif sim.mature():
				var crop_name: String = sim.crop().get("label", "crop")
				var coins := sim.harvest()
				Game.spend_action("harvest")
				if plot.owner_id == "sarah":
					_grant_help_credit(plot, "harvest")
					Game.notify("You bring in Sarah's %s for her." % crop_name.to_lower())
				else:
					Game.earn(coins)
					Game.notify("Harvested %s -- sold for %d coins." % [crop_name, coins])
			elif sim.can_harvest_early():
				_try_harvest_early(plot, sim)
			elif sim.has_crop():
				_inspect()
			else:
				Game.notify("Bare soil. Plant something, or check it with F.")
		"water":
			sim.water()
			Game.spend_action("water")
			_grant_help_credit(plot, "water")
			Game.notify("You give the plot a good soaking.")
		"seeds":
			if sim.has_crop():
				Game.notify("Something is already growing here.")
				return
			if sim.dead:
				Game.notify("Clear the dead plant first (Hand).")
				return
			var crop_id: String = SEED_CYCLE[seed_index]
			if not Game.take_item("seed_" + crop_id):
				Game.notify("No %s seeds left. The supply crate sells more." % crop_id)
				return
			sim.plant(crop_id)
			Game.spend_action("plant")
			Game.notify("Planted %s." % crop_id)
		"compost":
			if not Game.take_item("compost"):
				Game.notify("Out of compost.")
				return
			sim.apply_compost()
			Game.spend_action("compost")
			Game.notify("You work compost into the soil.")
		"manure":
			if not Game.take_item("manure"):
				Game.notify("Out of manure.")
				return
			var result := sim.apply_manure()
			Game.spend_action("manure")
			if result == "burned":
				Game.notify("Rich stuff -- but the young plant's leaves scorch at the edges!")
			else:
				Game.notify("You spread manure. The soil will thank you.")
		"mulch":
			if not Game.take_item("mulch"):
				Game.notify("Out of mulch.")
				return
			sim.apply_mulch()
			Game.spend_action("mulch")
			Game.notify("A thick mulch blanket now shades the soil.")
		"cover":
			if sim.covered:
				Game.notify("Already covered. Use the Hand to uncover.")
				return
			if not Game.take_item("cover"):
				Game.notify("No row covers left. The supply crate sells them.")
				return
			sim.set_cover(true)
			Game.spend_action("cover")
			_grant_help_credit(plot, "cover")
			Game.notify("Row cover pinned down tight.")

## Salvaging a not-yet-ripe crop destroys it for half value -- too costly to
## trigger on a single accidental click. First press arms it (with a toast);
## a second press on the same plot within a few seconds confirms it.
func _try_harvest_early(plot: Plot, sim: PlotSim) -> void:
	if _pending_harvest_plot == plot and _pending_harvest_timer > 0.0:
		var crop_name: String = sim.crop().get("label", "crop")
		var coins := sim.harvest()
		Game.spend_action("harvest")
		_pending_harvest_plot = null
		_pending_harvest_timer = 0.0
		if plot.owner_id == "sarah":
			_grant_help_credit(plot, "harvest")
		else:
			Game.earn(coins)
		Game.notify("Harvested %s early -- %d coins. It hadn't finished ripening." % [crop_name, coins])
	else:
		_pending_harvest_plot = plot
		_pending_harvest_timer = 3.0
		Game.notify("Still growing. Hand it again to salvage now at roughly half value.")

func _grant_help_credit(plot: Plot, action: String) -> void:
	if plot.owner_id == "sarah":
		var sarah := get_tree().get_first_node_in_group("sarah")
		if sarah:
			sarah.on_player_helped(plot, action)

func _inspect() -> void:
	var plot := target_plot()
	if plot == null:
		return
	Game.spend_action("inspect")
	var text := "%s\n\n%s" % [Qualitative.crop_report(plot.sim), Qualitative.soil_feel(plot.sim)]
	get_tree().call_group("hud", "show_inspection", text)

func _interact() -> void:
	var kind := target_interact_kind()
	match kind:
		"sleep":
			get_tree().call_group("hud", "confirm_sleep")
		"shop":
			get_tree().call_group("hud", "open_shop")
		"sarah":
			var sarah := get_tree().get_first_node_in_group("sarah")
			if sarah:
				sarah.talk_to()

func tool_label() -> String:
	var t: Dictionary = TOOLS[tool_index]
	if t["id"] == "seeds":
		return "Seeds: %s" % SEED_CYCLE[seed_index].capitalize()
	return t["label"]
