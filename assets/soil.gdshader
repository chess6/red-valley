shader_type spatial;
// Field plot soil. Colour communicates soil type; darkness + sheen
// communicate moisture; mulch adds a straw-flecked cover; frost whitens.

global uniform float frost_amount;

uniform vec3 dry_color: source_color = vec3(0.55, 0.42, 0.28);
uniform vec3 wet_color: source_color = vec3(0.25, 0.17, 0.10);
uniform float moisture = 0.4;
uniform float mulch = 0.0;
uniform float ridges = 6.0;

float hash2(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

varying vec3 local_pos;

void vertex() {
	local_pos = VERTEX;
}

void fragment() {
	// furrow ridges
	float furrow = 0.5 + 0.5 * sin(local_pos.x * ridges * 3.14159);
	vec3 col = mix(dry_color, wet_color, clamp(moisture, 0.0, 1.0));
	col *= 0.82 + 0.18 * furrow;
	float speck = hash2(floor(local_pos.xz * 24.0));
	col *= 0.9 + 0.2 * speck;
	// mulch straw layer
	vec3 straw = vec3(0.62, 0.5, 0.28) * (0.75 + 0.5 * speck);
	col = mix(col, straw, mulch * 0.85);
	// standing-water sheen when saturated (kept subtle so it stays soil-brown)
	float glossy = smoothstep(0.88, 1.0, moisture);
	vec3 frosted = mix(col, vec3(0.82, 0.86, 0.9), 0.7);
	col = mix(col, frosted, frost_amount * (1.0 - mulch * 0.5));
	ALBEDO = col;
	ROUGHNESS = mix(0.95, 0.5, glossy);
	SPECULAR = mix(0.2, 0.35, glossy);
}
