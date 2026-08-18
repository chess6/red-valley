class_name Plot
extends Node3D
## Scene-side wrapper for one PlotSim: soil visuals, crop stage meshes,
## wilt/health tinting, mulch and row-cover props, and a collision body so
## the player can aim at it.

const PLOT_SIZE := 1.8

static var _soil_shader: Shader
static var _crop_scenes := {}     # path -> PackedScene

var sim: PlotSim
var owner_id: String = "player"   # "player" or "sarah"

var _soil_mat: ShaderMaterial
var _crop_holder: Node3D
var _cover_node: Node3D
var _current_stage_key := ""
var _tint_mats: Array[StandardMaterial3D] = []
var _tint_bases: Array[Color] = []

const STAGE_MESHES := {
	"sprout": "res://assets/models/crop_sprout.glb",
	"dead": "res://assets/models/crop_dead.glb",
}

const SOIL_COLORS := {
	PlotSim.Soil.SANDY: {"dry": Color(0.72, 0.62, 0.44), "wet": Color(0.42, 0.34, 0.22)},
	PlotSim.Soil.LOAM: {"dry": Color(0.48, 0.36, 0.24), "wet": Color(0.20, 0.13, 0.08)},
	PlotSim.Soil.CLAY: {"dry": Color(0.58, 0.38, 0.26), "wet": Color(0.30, 0.16, 0.10)},
}

static func make(soil_type: int, owner_name: String) -> Plot:
	var p := Plot.new()
	p.sim = PlotSim.new(soil_type)
	p.owner_id = owner_name
	return p

func _ready() -> void:
	if _soil_shader == null:
		_soil_shader = load("res://assets/soil.gdshader")
	# soil bed
	var bed := MeshInstance3D.new()
	var mesh := BoxMesh.new()
	mesh.size = Vector3(PLOT_SIZE, 0.22, PLOT_SIZE)
	bed.mesh = mesh
	bed.position.y = 0.11
	_soil_mat = ShaderMaterial.new()
	_soil_mat.shader = _soil_shader
	var colors: Dictionary = SOIL_COLORS[sim.soil]
	_soil_mat.set_shader_parameter("dry_color", colors["dry"])
	_soil_mat.set_shader_parameter("wet_color", colors["wet"])
	_soil_mat.set_shader_parameter("ridges", 3.0)
	bed.material_override = _soil_mat
	add_child(bed)
	# crop holder
	_crop_holder = Node3D.new()
	_crop_holder.position.y = 0.22
	add_child(_crop_holder)
	# row cover prop
	_cover_node = _load_scene("res://assets/models/row_cover.glb")
	_cover_node.position.y = 0.25
	_cover_node.visible = false
	add_child(_cover_node)
	# aim/interaction body
	var body := StaticBody3D.new()
	body.collision_layer = 2
	body.collision_mask = 0
	var shape := CollisionShape3D.new()
	var box := BoxShape3D.new()
	box.size = Vector3(PLOT_SIZE, 0.9, PLOT_SIZE)
	shape.shape = box
	shape.position.y = 0.45
	body.add_child(shape)
	body.set_meta("plot", self)
	add_child(body)
	Farm.register_plot(self)
	refresh_visuals()

func _exit_tree() -> void:
	Farm.unregister_plot(self)

func _load_scene(path: String) -> Node3D:
	if not _crop_scenes.has(path):
		_crop_scenes[path] = load(path)
	return _crop_scenes[path].instantiate()

func _stage_key() -> String:
	if sim.crop_id == "":
		return ""
	if sim.dead:
		return "dead"
	if sim.growth < 0.12:
		return "sprout"
	var stage := "young"
	if sim.growth >= 1.0:
		stage = "mature"
	elif sim.growth >= 0.55:
		stage = "grown"
	return "crop_%s_%s" % [sim.crop_id, stage]

func refresh_visuals() -> void:
	_soil_mat.set_shader_parameter("moisture", sim.moisture)
	_soil_mat.set_shader_parameter("mulch", sim.mulch)
	_cover_node.visible = sim.covered
	var key := _stage_key()
	if key != _current_stage_key:
		_current_stage_key = key
		for child in _crop_holder.get_children():
			child.queue_free()
		_tint_mats.clear()
		_tint_bases.clear()
		if key != "":
			var path: String = STAGE_MESHES.get(key, "res://assets/models/%s.glb" % key)
			var inst := _load_scene(path)
			_crop_holder.add_child(inst)
			_collect_tintable(inst)
	_apply_crop_condition()

## Duplicate materials once per stage instance so we can tint per plot.
func _collect_tintable(node: Node) -> void:
	if node is MeshInstance3D:
		var mi: MeshInstance3D = node
		for s in mi.mesh.get_surface_count():
			var m := mi.mesh.surface_get_material(s)
			if m is StandardMaterial3D:
				var dup: StandardMaterial3D = m.duplicate()
				mi.set_surface_override_material(s, dup)
				_tint_mats.append(dup)
				_tint_bases.append(dup.albedo_color)
	for child in node.get_children():
		_collect_tintable(child)

func _apply_crop_condition() -> void:
	if _current_stage_key == "" or _current_stage_key == "dead":
		_crop_holder.scale = Vector3.ONE
		_crop_holder.rotation = Vector3.ZERO
		return
	var wilt := sim.wilt_level()
	var health := sim.health
	# droop: shrink vertically and sag slightly when wilted
	var sag := 1.0 - 0.30 * wilt
	if sim.covered:
		sag *= 0.5  # tucked under the fleece
	_crop_holder.scale = Vector3(1.0, sag, 1.0)
	_crop_holder.rotation.z = 0.10 * wilt
	# tint: yellow when wilted/starved, brown when frostbitten
	for i in _tint_mats.size():
		var base := _tint_bases[i]
		var c := base
		c = c.lerp(Color(0.75, 0.68, 0.25), wilt * 0.45)
		c = c.lerp(Color(0.65, 0.6, 0.5), (1.0 - health) * 0.3)
		c = c.lerp(Color(0.35, 0.25, 0.14), sim.frostbitten * 0.6)
		_tint_mats[i].albedo_color = c
