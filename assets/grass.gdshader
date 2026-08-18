shader_type spatial;
// Valley grass: low-poly flat colour with soft large-scale variation,
// darkened when wet, whitened by frost.

global uniform float frost_amount;
global uniform float wetness;

uniform vec3 base_color: source_color = vec3(0.30, 0.45, 0.20);
uniform vec3 alt_color: source_color = vec3(0.41, 0.52, 0.22);
uniform float patch_scale = 0.04;

float hash2(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	vec2 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash2(i), hash2(i + vec2(1, 0)), u.x),
		mix(hash2(i + vec2(0, 1)), hash2(i + vec2(1, 1)), u.x), u.y);
}

varying vec3 world_pos;

void vertex() {
	world_pos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	float n = vnoise(world_pos.xz * patch_scale);
	float n2 = vnoise(world_pos.xz * patch_scale * 7.0);
	vec3 col = mix(base_color, alt_color, n * 0.8 + n2 * 0.2);
	col *= 1.0 - 0.25 * wetness;
	// frost: sparkling white dusting
	vec3 frosted = mix(col, vec3(0.85, 0.88, 0.92), 0.65 + 0.2 * n2);
	col = mix(col, frosted, frost_amount);
	ALBEDO = col;
	ROUGHNESS = mix(0.95, 0.55, wetness);
}
