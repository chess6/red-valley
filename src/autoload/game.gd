extends Node
## Global clock, labor-as-time, and the player's inventory.
##
## Time is the core resource: 1 real second = TIME_SCALE game minutes while
## playing, and farm actions instantly consume extra game minutes, so a day
## never has room for everything.

signal day_changed(day: int)
signal time_advanced(minutes: float)  # emitted for any jump (actions, waiting)
signal slept
signal coins_changed(coins: int)
signal inventory_changed
signal toast(message: String)

const TIME_SCALE := 1.15          # game minutes per real second
const WAKE_HOUR := 6.0
const COLLAPSE_HOUR := 2.0        # 02:00 -- you can't stay up past this

var day: int = 1
var minutes: float = WAKE_HOUR * 60.0   # minutes since midnight
var running: bool = true                # false while menus/dialogue open

var coins: int = 40
var inventory := {
	"seed_tomato": 6,
	"seed_cabbage": 6,
	"seed_potato": 6,
	"seed_wheat": 8,
	"compost": 4,
	"manure": 2,
	"mulch": 4,
	"cover": 5,
}

const SHOP_PRICES := {
	"seed_tomato": 6, "seed_cabbage": 8, "seed_potato": 5, "seed_wheat": 3,
	"compost": 8, "manure": 6, "mulch": 5, "cover": 15,
}

## Minutes of labor each action costs (walking costs real time already).
const ACTION_MINUTES := {
	"water": 8.0,
	"plant": 12.0,
	"harvest": 12.0,
	"compost": 10.0,
	"manure": 10.0,
	"mulch": 10.0,
	"cover": 18.0,
	"uncover": 8.0,
	"inspect": 2.0,
}

func hour() -> float:
	return minutes / 60.0

func clock_text() -> String:
	var h := int(minutes / 60.0) % 24
	var m := int(minutes) % 60
	return "%02d:%02d" % [h, m]

func is_night() -> bool:
	return hour() >= 21.0 or hour() < 5.5

func _process(delta: float) -> void:
	if not running:
		return
	_advance(delta * TIME_SCALE)
	# Forced collapse in the small hours: you black out and wake at 06:00.
	if hour() >= COLLAPSE_HOUR and hour() < WAKE_HOUR - 0.01:
		toast.emit("You worked yourself into the ground and collapsed into bed.")
		sleep_until_morning()

func _advance(game_minutes: float) -> void:
	# Step in <=10-minute chunks so the farm sim integrates smoothly.
	var remaining := game_minutes
	while remaining > 0.0:
		var step := minf(remaining, 10.0)
		remaining -= step
		minutes += step
		Farm.tick_world(step)
		if minutes >= 24.0 * 60.0:
			minutes -= 24.0 * 60.0
			day += 1
			Farm.on_new_day()
			day_changed.emit(day)

## An action eats clock time. Returns false if there isn't a sensible amount
## of day left (night blocks field work).
func spend_action(action: String) -> bool:
	var cost: float = ACTION_MINUTES.get(action, 5.0)
	_advance(cost)
	time_advanced.emit(cost)
	return true

func wait_one_hour() -> void:
	_advance(60.0)
	time_advanced.emit(60.0)

func sleep_until_morning() -> void:
	var target := WAKE_HOUR * 60.0
	var to_advance: float
	if minutes < target:
		to_advance = target - minutes
	else:
		to_advance = (24.0 * 60.0 - minutes) + target
	_advance(to_advance)
	slept.emit()

# ------------------------------------------------------------- inventory

func has_item(id: String, count: int = 1) -> bool:
	return inventory.get(id, 0) >= count

func take_item(id: String, count: int = 1) -> bool:
	if not has_item(id, count):
		return false
	inventory[id] -= count
	inventory_changed.emit()
	return true

func give_item(id: String, count: int = 1) -> void:
	inventory[id] = inventory.get(id, 0) + count
	inventory_changed.emit()

func earn(amount: int) -> void:
	coins += amount
	coins_changed.emit(coins)

func try_buy(id: String) -> bool:
	var price: int = SHOP_PRICES.get(id, 9999)
	if coins < price:
		return false
	coins -= price
	give_item(id)
	coins_changed.emit(coins)
	return true

func notify(message: String) -> void:
	toast.emit(message)
