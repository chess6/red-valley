extends CanvasLayer
## All UI: clock/weather chips, hotbar, qualitative prompts, inspection panel,
## dialogue, shop, sleep, pause, toasts, and the F3 debug overlay.
## Styled after the concept art: dark rounded chips over the 3D world.

var player: Player
var day_label: Label
var coins_label: Label
var weather_label: Label
var forecast_label: Label
var frost_banner: PanelContainer
var frost_banner_label: Label
var target_label: Label
var prompt_label: Label
var toast_box: VBoxContainer
var hotbar: HBoxContainer
var inspect_panel: PanelContainer
var inspect_label: Label
var dialogue_panel: PanelContainer
var dialogue_text: Label
var dialogue_buttons: VBoxContainer
var shop_panel: PanelContainer
var shop_list: VBoxContainer
var sleep_panel: PanelContainer
var pause_panel: PanelContainer
var debug_label: Label
var _sleep_snapshot: Array = []
var _modal_open := false

func _ready() -> void:
	add_to_group("hud")
	layer = 10
	player = get_tree().get_first_node_in_group("player")
	_build()
	Game.toast.connect(_on_toast)
	Game.coins_changed.connect(func(c): coins_label.text = "%d coins" % c)
	Game.day_changed.connect(func(_d): _flash_new_day())

# ------------------------------------------------------------ construction

func _chip() -> PanelContainer:
	var p := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.08, 0.10, 0.82)
	sb.corner_radius_top_left = 8
	sb.corner_radius_top_right = 8
	sb.corner_radius_bottom_left = 8
	sb.corner_radius_bottom_right = 8
	sb.content_margin_left = 12
	sb.content_margin_right = 12
	sb.content_margin_top = 8
	sb.content_margin_bottom = 8
	p.add_theme_stylebox_override("panel", sb)
	return p

func _label(text := "", size := 16, color := Color.WHITE) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l

func _build() -> void:
	var root := Control.new()
	root.set_anchors_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(root)

	# top-left: day/time + coins
	var tl := VBoxContainer.new()
	tl.position = Vector2(16, 14)
	tl.add_theme_constant_override("separation", 6)
	root.add_child(tl)
	var chip1 := _chip()
	day_label = _label("Day 1  06:00", 20)
	chip1.add_child(day_label)
	tl.add_child(chip1)
	var chip2 := _chip()
	coins_label = _label("%d coins" % Game.coins, 15, Color(0.95, 0.85, 0.5))
	chip2.add_child(coins_label)
	tl.add_child(chip2)

	# top-right: weather + forecast
	var tr := VBoxContainer.new()
	tr.set_anchors_preset(Control.PRESET_TOP_RIGHT)
	tr.position = Vector2(-16, 14)
	tr.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	tr.add_theme_constant_override("separation", 6)
	root.add_child(tr)
	var wchip := _chip()
	var wv := VBoxContainer.new()
	weather_label = _label("Weather: Clear", 16)
	forecast_label = _label("Tomorrow: ...", 14, Color(0.8, 0.85, 0.95))
	wv.add_child(weather_label)
	wv.add_child(forecast_label)
	wchip.add_child(wv)
	tr.add_child(wchip)

	# frost warning banner (top center)
	frost_banner = _chip()
	var fb_style: StyleBoxFlat = frost_banner.get_theme_stylebox("panel")
	fb_style.bg_color = Color(0.10, 0.15, 0.30, 0.9)
	fb_style.border_color = Color(0.5, 0.7, 1.0)
	fb_style.border_width_bottom = 2
	frost_banner_label = _label("Frost warning!", 18, Color(0.75, 0.85, 1.0))
	frost_banner.add_child(frost_banner_label)
	frost_banner.set_anchors_preset(Control.PRESET_CENTER_TOP)
	frost_banner.position.y = 14
	frost_banner.grow_horizontal = Control.GROW_DIRECTION_BOTH
	frost_banner.visible = false
	root.add_child(frost_banner)

	# bottom center: target status + toasts + hotbar
	var bc := VBoxContainer.new()
	bc.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	bc.position.y = -16
	bc.grow_horizontal = Control.GROW_DIRECTION_BOTH
	bc.grow_vertical = Control.GROW_DIRECTION_BEGIN
	bc.add_theme_constant_override("separation", 8)
	bc.alignment = BoxContainer.ALIGNMENT_END
	root.add_child(bc)
	toast_box = VBoxContainer.new()
	toast_box.add_theme_constant_override("separation", 4)
	toast_box.alignment = BoxContainer.ALIGNMENT_END
	bc.add_child(toast_box)
	var target_chip := _chip()
	target_label = _label("", 15, Color(0.95, 0.95, 0.9))
	target_chip.add_child(target_label)
	var target_center := CenterContainer.new()
	target_center.add_child(target_chip)
	bc.add_child(target_center)
	hotbar = HBoxContainer.new()
	hotbar.add_theme_constant_override("separation", 6)
	var hb_center := CenterContainer.new()
	hb_center.add_child(hotbar)
	bc.add_child(hb_center)
	_build_hotbar()

	# bottom-right: context key prompts
	var br := VBoxContainer.new()
	br.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	br.position = Vector2(-16, -16)
	br.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	br.grow_vertical = Control.GROW_DIRECTION_BEGIN
	root.add_child(br)
	var pchip := _chip()
	prompt_label = _label("", 14, Color(0.9, 0.9, 0.85))
	pchip.add_child(prompt_label)
	br.add_child(pchip)

	# inspection panel (center-right, like concept art tooltip)
	inspect_panel = _chip()
	inspect_panel.set_anchors_preset(Control.PRESET_CENTER_RIGHT)
	inspect_panel.position = Vector2(-30, -60)
	inspect_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN
	inspect_label = _label("", 15)
	inspect_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	inspect_label.custom_minimum_size.x = 340
	inspect_panel.add_child(inspect_label)
	inspect_panel.visible = false
	root.add_child(inspect_panel)

	# debug overlay
	var dbg_chip := _chip()
	dbg_chip.set_anchors_preset(Control.PRESET_CENTER_LEFT)
	dbg_chip.position = Vector2(16, 0)
	debug_label = _label("", 13, Color(0.6, 1.0, 0.6))
	dbg_chip.add_child(debug_label)
	dbg_chip.visible = false
	dbg_chip.name = "DebugChip"
	root.add_child(dbg_chip)

	_build_modals(root)

func _build_hotbar() -> void:
	for i in Player.TOOLS.size():
		var chip := _chip()
		var v := VBoxContainer.new()
		v.name = "V"
		v.alignment = BoxContainer.ALIGNMENT_CENTER
		var num := _label(str(i + 1), 12, Color(0.6, 0.6, 0.6))
		num.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		var name_l := _label(Player.TOOLS[i]["label"], 13)
		name_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		name_l.name = "ToolName"
		var count_l := _label(" ", 12, Color(0.8, 0.8, 0.6))
		count_l.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		count_l.name = "Count"
		v.add_child(num)
		v.add_child(name_l)
		v.add_child(count_l)
		chip.add_child(v)
		chip.custom_minimum_size = Vector2(96, 0)
		hotbar.add_child(chip)

func _build_modals(root: Control) -> void:
	# dialogue
	dialogue_panel = _chip()
	dialogue_panel.set_anchors_preset(Control.PRESET_CENTER)
	dialogue_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	dialogue_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	var dv := VBoxContainer.new()
	dv.add_theme_constant_override("separation", 10)
	dialogue_text = _label("", 16)
	dialogue_text.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	dialogue_text.custom_minimum_size.x = 460
	dialogue_buttons = VBoxContainer.new()
	dialogue_buttons.add_theme_constant_override("separation", 6)
	dv.add_child(_label("Sarah", 18, Color(0.95, 0.75, 0.55)))
	dv.add_child(dialogue_text)
	dv.add_child(dialogue_buttons)
	dialogue_panel.add_child(dv)
	dialogue_panel.visible = false
	root.add_child(dialogue_panel)
	# shop
	shop_panel = _chip()
	shop_panel.set_anchors_preset(Control.PRESET_CENTER)
	shop_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	shop_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	var sv := VBoxContainer.new()
	sv.add_theme_constant_override("separation", 8)
	sv.add_child(_label("Supply crate", 18, Color(0.95, 0.85, 0.5)))
	shop_list = VBoxContainer.new()
	shop_list.add_theme_constant_override("separation", 4)
	sv.add_child(shop_list)
	var close := Button.new()
	close.text = "Close"
	close.pressed.connect(_close_modals)
	sv.add_child(close)
	shop_panel.add_child(sv)
	shop_panel.visible = false
	root.add_child(shop_panel)
	# sleep confirm
	sleep_panel = _chip()
	sleep_panel.set_anchors_preset(Control.PRESET_CENTER)
	sleep_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	sleep_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	var slv := VBoxContainer.new()
	slv.add_theme_constant_override("separation", 10)
	slv.add_child(_label("Turn in for the night?", 18))
	var sleep_btn := Button.new()
	sleep_btn.text = "Sleep until morning"
	sleep_btn.pressed.connect(_do_sleep)
	var stay := Button.new()
	stay.text = "Not yet"
	stay.pressed.connect(_close_modals)
	slv.add_child(sleep_btn)
	slv.add_child(stay)
	sleep_panel.add_child(slv)
	sleep_panel.visible = false
	root.add_child(sleep_panel)
	# pause
	pause_panel = _chip()
	pause_panel.set_anchors_preset(Control.PRESET_CENTER)
	pause_panel.grow_horizontal = Control.GROW_DIRECTION_BOTH
	pause_panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	var pv := VBoxContainer.new()
	pv.add_theme_constant_override("separation", 8)
	pv.add_child(_label("Red Valley -- paused", 20))
	pv.add_child(_label(
		"WASD move   Shift run   Mouse look\n" +
		"1-7 tools   Left click use tool   E interact   F inspect\n" +
		"T wait an hour   F3 raw numbers   Esc pause\n\n" +
		"Watch your soils: sand dries fast, clay drowns.\n" +
		"Frost kills the tender. Neighbours remember kindness.", 14, Color(0.8, 0.8, 0.8)))
	var resume := Button.new()
	resume.text = "Resume"
	resume.pressed.connect(_close_modals)
	var quit := Button.new()
	quit.text = "Quit game"
	quit.pressed.connect(func(): get_tree().quit())
	pv.add_child(resume)
	pv.add_child(quit)
	pause_panel.add_child(pv)
	pause_panel.visible = false
	root.add_child(pause_panel)

# ------------------------------------------------------------ per-frame

func _process(_delta: float) -> void:
	day_label.text = "Day %d   %s" % [Game.day, Game.clock_text()]
	weather_label.text = "Weather: %s" % _now_label()
	forecast_label.text = "Tonight & tomorrow: %s" % Weather.forecast_label()
	_update_frost_banner()
	_update_hotbar()
	_update_target_line()
	_update_debug()

func _now_label() -> String:
	var cond: Dictionary = Weather.current()
	if cond["raining"]:
		return "Heavy rain" if cond["rain_rate"] > 0.14 else "Rain"
	if Weather.frost_now():
		return "Frost"
	return Weather.today_label()

func _update_frost_banner() -> void:
	var f: Dictionary = Weather.forecast()
	var show: bool = f["frost_chance"] >= 0.3 and Game.hour() >= 12.0
	frost_banner.visible = show
	if show:
		frost_banner_label.text = "Frost warning!  %d%% chance tonight -- protect vulnerable crops." \
			% int(round(f["frost_chance"] * 100))

func _update_hotbar() -> void:
	for i in hotbar.get_child_count():
		var chip: PanelContainer = hotbar.get_child(i)
		var sb: StyleBoxFlat = chip.get_theme_stylebox("panel")
		var selected: bool = (i == player.tool_index)
		sb.bg_color = Color(0.25, 0.22, 0.12, 0.92) if selected else Color(0.07, 0.08, 0.10, 0.82)
		sb.border_width_top = 2 if selected else 0
		sb.border_color = Color(0.95, 0.85, 0.5)
		var name_l: Label = chip.get_node("V/ToolName")
		var count_l: Label = chip.get_node("V/Count")
		var tool: Dictionary = Player.TOOLS[i]
		match tool["id"]:
			"seeds":
				name_l.text = "Seeds: %s" % player.SEED_CYCLE[player.seed_index].capitalize()
				count_l.text = "x%d" % Game.inventory.get("seed_" + player.SEED_CYCLE[player.seed_index], 0)
			"compost", "manure", "mulch", "cover":
				name_l.text = tool["label"]
				count_l.text = "x%d" % Game.inventory.get(tool["id"], 0)
			_:
				name_l.text = tool["label"]
				count_l.text = " "

func _update_target_line() -> void:
	var plot: Plot = player.target_plot()
	var kind: String = player.target_interact_kind()
	if plot:
		target_label.get_parent().visible = true
		target_label.text = Qualitative.short_status(plot.sim)
		var tool_id: String = Player.TOOLS[player.tool_index]["id"]
		var verb: String = {
			"hand": "Harvest / clear / uncover", "water": "Water", "seeds": "Plant",
			"compost": "Compost", "manure": "Spread manure", "mulch": "Mulch", "cover": "Cover",
		}.get(tool_id, "Use")
		prompt_label.text = "[LMB] %s    [F] Inspect closely" % verb
	elif kind != "":
		target_label.get_parent().visible = true
		target_label.text = str(player.current_target.get_meta("prompt", ""))
		prompt_label.text = "[E] Interact"
	else:
		target_label.get_parent().visible = false
		prompt_label.text = "[1-7] Tools   [E] Interact   [Esc] Menu"

func _update_debug() -> void:
	var chip := debug_label.get_parent() as PanelContainer
	if not chip.visible:
		return
	var cond: Dictionary = Weather.current()
	var f: Dictionary = Weather.forecast()
	var lines: PackedStringArray = []
	lines.append("[DEBUG]  temp %.1fC  sun %.2f  rain %.2f  cloud %.2f" %
		[cond["temp"], cond["sun"], cond["rain_rate"], cond["cloud"]])
	lines.append("tonight low %.1fC  frost%% %.0f  rain%% %.0f" %
		[Weather.today()["t_night"], f["frost_chance"] * 100, f["rain_chance"] * 100])
	var plot: Plot = player.target_plot()
	if plot:
		var s: PlotSim = plot.sim
		lines.append("plot(%s/%s): moist %.2f fert %.2f mulch %.2f cover %s" %
			[s.soil_params()["label"], plot.owner_id, s.moisture, s.fertility, s.mulch, s.covered])
		if s.crop_id != "":
			lines.append("crop %s: growth %.2f health %.2f wilt %.2f dead %s" %
				[s.crop_id, s.growth, s.health, s.wilt_level(), s.dead])
	var sarah := get_tree().get_first_node_in_group("sarah")
	if sarah:
		lines.append("sarah: reciprocity %.1f  state %d  queue %d" %
			[sarah.reciprocity, sarah.state, sarah._task_queue.size()])
	debug_label.text = "\n".join(lines)

func _input(event: InputEvent) -> void:
	if event.is_action_pressed("debug_toggle"):
		var chip := debug_label.get_parent() as PanelContainer
		chip.visible = not chip.visible
	if event.is_action_pressed("pause"):
		if _modal_open:
			_close_modals()
		else:
			_open_modal(pause_panel)
	if event.is_action_pressed("inspect") and inspect_panel.visible and not _modal_open:
		pass  # player re-inspects; panel refreshes via show_inspection

# ------------------------------------------------------------ modal plumbing

func _open_modal(panel: PanelContainer) -> void:
	_close_modals()
	panel.visible = true
	_modal_open = true
	Game.running = false
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _close_modals() -> void:
	for p in [dialogue_panel, shop_panel, sleep_panel, pause_panel]:
		p.visible = false
	_modal_open = false
	Game.running = true
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED

# ------------------------------------------------------------ features

func _on_toast(message: String) -> void:
	var chip := _chip()
	var l := _label(message, 14, Color(0.95, 0.95, 0.9))
	chip.add_child(l)
	var center := CenterContainer.new()
	center.add_child(chip)
	toast_box.add_child(center)
	var tween := create_tween()
	tween.tween_interval(3.4)
	tween.tween_property(chip, "modulate:a", 0.0, 0.8)
	tween.tween_callback(center.queue_free)
	if toast_box.get_child_count() > 4:
		toast_box.get_child(0).queue_free()

func show_inspection(text: String) -> void:
	inspect_label.text = text
	inspect_panel.visible = true
	var tween := create_tween()
	tween.tween_interval(7.0)
	tween.tween_callback(func():
		if inspect_label.text == text:
			inspect_panel.visible = false)

func confirm_sleep() -> void:
	_open_modal(sleep_panel)

func _do_sleep() -> void:
	_sleep_snapshot = []
	for p in Farm.plots_of("player"):
		_sleep_snapshot.append({"plot": p, "dead": p.sim.dead, "bitten": p.sim.frostbitten > 0.2})
	_close_modals()
	Game.sleep_until_morning()
	_morning_report()

func _morning_report() -> void:
	var died := 0
	var bitten := 0
	for snap in _sleep_snapshot:
		var p: Plot = snap["plot"]
		if not is_instance_valid(p):
			continue
		if p.sim.dead and not snap["dead"]:
			died += 1
		elif p.sim.frostbitten > 0.2 and not snap["bitten"] and not p.sim.dead:
			bitten += 1
	if died > 0 and bitten > 0:
		Game.notify("A hard frost in the night. %d plants dead, %d more scorched." % [died, bitten])
	elif died > 0:
		Game.notify("The frost took %d of your plants overnight." % died)
	elif bitten > 0:
		Game.notify("Frost nipped %d of your plants overnight." % bitten)
	else:
		Game.notify("A new morning on the farm. Weather: %s." % Weather.today_label())

func _flash_new_day() -> void:
	pass  # day label updates every frame; hook kept for future fanfare

func open_shop() -> void:
	for child in shop_list.get_children():
		child.queue_free()
	for id in Game.SHOP_PRICES:
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 12)
		var pretty: String = id.replace("seed_", "").capitalize()
		if id.begins_with("seed_"):
			pretty += " seeds"
		var l := _label("%s -- %d coins  (have %d)" % [pretty, Game.SHOP_PRICES[id], Game.inventory.get(id, 0)], 14)
		l.custom_minimum_size.x = 280
		var b := Button.new()
		b.text = "Buy"
		var item_id: String = id
		b.pressed.connect(func():
			if Game.try_buy(item_id):
				open_shop()
			else:
				Game.notify("Not enough coins."))
		row.add_child(l)
		row.add_child(b)
		shop_list.add_child(row)
	_open_modal(shop_panel)

func open_dialogue(sarah) -> void:
	for child in dialogue_buttons.get_children():
		child.queue_free()
	dialogue_text.text = sarah.her_needs_text() + "\n\n" + sarah.reciprocity_text()
	var opts: Array = []
	if Weather.frost_warning_active():
		opts.append(["Ask her to help cover crops tonight (a big favour)", "cover"])
	opts.append(["Ask her to help with watering (a favour)", "water"])
	opts.append(["Just chat", "chat"])
	opts.append(["Leave", "leave"])
	for opt in opts:
		var b := Button.new()
		b.text = opt[0]
		var choice: String = opt[1]
		b.pressed.connect(func(): _dialogue_choice(sarah, choice))
		dialogue_buttons.add_child(b)
	_open_modal(dialogue_panel)

func _dialogue_choice(sarah, choice: String) -> void:
	match choice:
		"leave":
			_close_modals()
		"chat":
			dialogue_text.text = sarah.her_needs_text()
		"cover", "water":
			dialogue_text.text = sarah.request_help(choice)
