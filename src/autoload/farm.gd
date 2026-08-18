extends Node
## Registry of every plot in the world (player's and Sarah's) and the single
## place the simulation is ticked from, so realtime play, action time-costs,
## and sleeping all integrate identically.

signal plots_changed

var plots: Array = []          # Plot nodes (each has .sim: PlotSim, .owner_id)

func register_plot(plot) -> void:
	plots.append(plot)

func unregister_plot(plot) -> void:
	plots.erase(plot)

func plots_of(owner_id: String) -> Array:
	return plots.filter(func(p): return p.owner_id == owner_id)

## Called by Game for every chunk of elapsed game time.
func tick_world(game_minutes: float) -> void:
	var dt_hours := game_minutes / 60.0
	var env: Dictionary = Weather.current()
	for p in plots:
		p.sim.tick(dt_hours, env)

func on_new_day() -> void:
	for p in plots:
		p.sim.end_of_day()
	plots_changed.emit()
