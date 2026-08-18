class_name Sarah
extends CharacterBody3D
## The neighbour. She works her own field visibly, remembers actual help
## (reciprocity), and will physically walk over and work your plots when
## asked -- if you've earned it.

const SPEED := 3.4
const GATE := Vector3(23.5, 0, -2.0)   # gap in the boundary fence
const HOME := Vector3(41, 0, 0)

enum State { IDLE, WALK, WORK }

var reciprocity := 1.0
var earned_today := 0.0
var state: int = State.IDLE
var _task_queue: Array = []       # [{plot, action}]
var _current_task: Dictionary = {}
var _walk_path: Array = []        # Vector3 waypoints
var _work_left := 0.0
var _visual: Node3D
var _bob_t := 0.0
var _idle_timer := 3.0
var _said_busy := false

func _ready() -> void:
	add_to_group("sarah")
	collision_layer = 0
	collision_mask = 1
	var cs := CollisionShape3D.new()
	var cap := CapsuleShape3D.new()
	cap.radius = 0.35
	cap.height = 1.7
	cs.shape = cap
	cs.position.y = 0.85
	add_child(cs)
	_visual = load("res://assets/models/sarah.glb").instantiate()
	add_child(_visual)
	# talk target
	var body := StaticBody3D.new()
	body.collision_layer = 2
	body.collision_mask = 0
	var tcs := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(1.2, 1.9, 1.2)
	tcs.shape = box
	tcs.position.y = 0.95
	body.add_child(tcs)
	body.set_meta("interact", "sarah")
	body.set_meta("prompt", "Talk to Sarah")
	add_child(body)
	Game.day_changed.connect(_on_new_day)

func _on_new_day(_day: int) -> void:
	earned_today = 0.0
	_said_busy = false

# ---------------------------------------------------------------- movement

func _physics_process(delta: float) -> void:
	if not Game.running:
		return
	match state:
		State.WALK:
			_walk(delta)
		State.WORK:
			_work(delta)
		State.IDLE:
			_idle(delta)
	if not is_on_floor():
		velocity.y -= 22.0 * delta
	else:
		velocity.y = 0
	move_and_slide()

func _walk(delta: float) -> void:
	if _walk_path.is_empty():
		velocity.x = 0; velocity.z = 0
		if not _current_task.is_empty():
			state = State.WORK
			_work_left = 2.0
		else:
			state = State.IDLE
		return
	var target: Vector3 = _walk_path[0]
	var to := target - global_position
	to.y = 0
	if to.length() < 0.6:
		_walk_path.pop_front()
		return
	var dir := to.normalized()
	velocity.x = dir.x * SPEED
	velocity.z = dir.z * SPEED
	_face_move(delta)

func _face_move(delta: float) -> void:
	var planar := Vector3(velocity.x, 0, velocity.z)
	if planar.length() > 0.3:
		_visual.rotation.y = lerp_angle(_visual.rotation.y, atan2(planar.x, planar.z), 8 * delta)
		_bob_t += delta * planar.length() * 2.2
		_visual.position.y = absf(sin(_bob_t)) * 0.05

func _work(delta: float) -> void:
	velocity.x = 0; velocity.z = 0
	_bob_t += delta * 7.0
	_visual.rotation.x = 0.25 + sin(_bob_t) * 0.12   # bent over, working
	_work_left -= delta
	if _work_left <= 0.0:
		_visual.rotation.x = 0.0
		_finish_task()

func _idle(delta: float) -> void:
	velocity.x = 0; velocity.z = 0
	_visual.rotation.x = 0.0
	_idle_timer -= delta
	if _idle_timer <= 0.0:
		_idle_timer = randf_range(4.0, 9.0)
		_decide()

## Route around the boundary fence via the gate when crossing farms.
func _route_to(pos: Vector3) -> Array:
	var here := global_position
	var crossing := (here.x > 23.0) != (pos.x > 23.0)
	if crossing:
		return [GATE, pos]
	return [pos]

func _go_do(plot: Plot, action: String) -> void:
	_current_task = {"plot": plot, "action": action}
	_walk_path = _route_to(plot.global_position + Vector3(1.1, 0, 0))
	state = State.WALK

# ---------------------------------------------------------------- decisions

func _decide() -> void:
	if not _task_queue.is_empty():
		var t: Dictionary = _task_queue.pop_front()
		_go_do(t["plot"], t["action"])
		return
	# Evening frost prep on her own farm.
	var evening := Game.hour() >= 16.0
	if evening and Weather.frost_warning_active():
		for p in Farm.plots_of("sarah"):
			var sim: PlotSim = p.sim
			if sim.has_crop() and not sim.covered and sim.crop()["frost_threshold_c"] > -3.0:
				_go_do(p, "cover")
				return
	# Water her driest crops in the morning/afternoon.
	if Game.hour() >= 7.0 and Game.hour() <= 19.0:
		for p in Farm.plots_of("sarah"):
			var sim2: PlotSim = p.sim
			if sim2.has_crop() and sim2.moisture < sim2.crop()["moisture_lo"] - 0.05:
				_go_do(p, "water")
				return
		# Harvest anything ready.
		for p in Farm.plots_of("sarah"):
			if p.sim.mature():
				_go_do(p, "harvest")
				return
	# Otherwise drift around her yard.
	if global_position.distance_to(HOME) > 12.0:
		_walk_path = _route_to(HOME)
		state = State.WALK
	elif randf() < 0.5:
		var wander := HOME + Vector3(randf_range(-5, 5), 0, randf_range(-4, 6))
		_walk_path = _route_to(wander)
		state = State.WALK

func _finish_task() -> void:
	var plot: Plot = _current_task.get("plot")
	var action: String = _current_task.get("action", "")
	_current_task = {}
	state = State.IDLE
	_idle_timer = 1.0
	if plot == null or not is_instance_valid(plot):
		return
	var sim: PlotSim = plot.sim
	var yours := plot.owner_id == "player"
	match action:
		"water":
			sim.water()
			if yours:
				Game.notify("Sarah watered one of your plots.")
		"cover":
			if not sim.covered and sim.has_crop():
				sim.set_cover(true)
				if yours:
					Game.notify("Sarah pinned a row cover over your %s." % sim.crop()["label"].to_lower())
		"harvest":
			if sim.mature():
				sim.harvest()   # her own produce, her own coin
	plot.refresh_visuals()

# ---------------------------------------------------------------- social

## Called by the player when they act on one of Sarah's plots.
func on_player_helped(plot: Plot, action: String) -> void:
	var sim: PlotSim = plot.sim
	var useful := false
	match action:
		"water":
			useful = sim.has_crop() and sim.moisture < sim.crop()["moisture_lo"] + 0.28
		"cover":
			useful = Weather.frost_warning_active() and sim.has_crop()
		"harvest":
			useful = true
	var gain := 1.0 if useful else 0.25
	gain = minf(gain, maxf(0.0, 5.0 - earned_today))
	if gain <= 0.0:
		return
	earned_today += gain
	reciprocity += gain
	if useful:
		Game.notify("Sarah waves gratefully from across the field.  (favour earned)")

func talk_to() -> void:
	get_tree().call_group("hud", "open_dialogue", self)

func reciprocity_text() -> String:
	if reciprocity >= 6.0:
		return "Sarah owes you more favours than she can count."
	elif reciprocity >= 3.0:
		return "Sarah clearly remembers your help."
	elif reciprocity >= 1.0:
		return "You and Sarah are on friendly terms."
	return "Sarah barely knows you yet."

func her_needs_text() -> String:
	var dry := 0
	var ripe := 0
	for p in Farm.plots_of("sarah"):
		var sim: PlotSim = p.sim
		if sim.has_crop() and sim.moisture < sim.crop()["moisture_lo"]:
			dry += 1
		if sim.mature():
			ripe += 1
	if dry >= 2:
		return "\"My field's drying out faster than I can carry water. If you happen to be passing with a can...\""
	if ripe >= 2:
		return "\"Half my crop is sitting ripe in the field. I could use a hand bringing it in.\""
	if Weather.frost_warning_active():
		return "\"Cold air tonight, I can smell it. Check your tender plants before dark.\""
	return "\"Fine day for working the land. My grandmother used to say: know your soil before you blame the sky.\""

## Player asks for help. kind: "cover" or "water". Returns response line.
func request_help(kind: String) -> String:
	var cost := 3.0 if kind == "cover" else 2.0
	if reciprocity < cost:
		return "\"I'd like to help, truly -- but I've got my hands full with my own field. Lend me a hand sometime and I'll return it.\""
	var targets: Array = []
	for p in Farm.plots_of("player"):
		var sim: PlotSim = p.sim
		match kind:
			"cover":
				if sim.has_crop() and not sim.covered and not sim.dead and sim.crop()["frost_threshold_c"] > -3.0:
					targets.append(p)
			"water":
				if sim.has_crop() and not sim.dead and sim.moisture < sim.crop()["moisture_lo"]:
					targets.append(p)
	if targets.is_empty():
		return "\"Looks like there's nothing over there that needs me right now.\""
	var take: int = mini(targets.size(), 4 if kind == "cover" else 5)
	reciprocity -= cost
	_task_queue.clear()
	for i in take:
		_task_queue.append({"plot": targets[i], "action": kind})
	_idle_timer = 0.5
	state = State.IDLE
	if kind == "cover":
		return "\"Frost tonight? Say no more. I've got spare fleece -- I'll see to %d beds. You take the rest.\"" % take
	return "\"Go on, I'll water %d of the thirstiest beds for you.\"" % take

func is_busy_helping() -> bool:
	return not _task_queue.is_empty() or not _current_task.is_empty()
