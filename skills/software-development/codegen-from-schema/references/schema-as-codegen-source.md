# Making a JSON-Schema a true codegen source of truth

The generator reads one `x-` realization block per Rust-representable `$def` in
addition to the schema's standard `type`/`enum`/`properties` (which stay as the
wire documentation). Keep the standard keywords untouched (a completeness guard
may read the `$defs` keys); add `description` + `x-rust` innocuously.

## The `x-rust` block per kind

`"kind"` is one of `enum | struct | tagged_enum | alias`. Common flags:
`"copy"` / `"eq"` decide whether the derive line carries `Copy` / `Eq`
(enums and field-less structs can be `Eq`; any struct with an `f64` cannot
— `f64` implements neither `Eq` nor `Hash`).

- **enum** — `{ rename_all: "snake_case" | "SCREAMING_SNAKE_CASE", copy, eq,
  variant_docs?, variant_names? }`. Variant NAMES are derived from the ordered
  `enum` array + rename_case, UNLESS a `variant_names` map (wire value → Rust
  name) overrides one (needed when a wire value holds a char an identifier
  cannot, e.g. `reputation.de_list` → `ReputationDeList`).
- **struct** — `{ copy, eq, fields: [ { name, ty, rust_name?, doc?, serde? } ]
  }`. `ty` is the explicit Rust type string (`u16`, `String`, `Vec<Finding>`,
  `Option<EventType>`, `serde_json::Value`, `BTreeMap<String, u32>`, a
  cross-crate path like `steadfaste_abi::enums::Trust`). `serde` is the list of
  `#[serde(...)]` attribute fragments. Non-required fields are typed
  `Option<T>` with `["skip_serializing_if = \"Option::is_none\""]`. The
  `fields` array order IS the emitted field order (see the BTreeMap pitfall in
  the umbrella).
- **tagged_enum** — `{ tag, rename_all, copy, eq, tagged_variants:
  [ { tag, doc?, fields: [...] } ] }` for an internally-tagged Rust enum
  (`#[serde(tag = "primitive", rename_all = "snake_case")]`). Put the variant
  doc on the VARIANT, not on its first field.
- **alias** — `{ ty }` emits `pub type Name = ty;` for a bounded-integer
  pseudo-type (`TrustTier` → `pub type TrustTier = u8;`) that a `$ref` field
  uses.

## Name overrides

- Per-`$def` `"name"` in `x-rust` overrides the Rust type name for a def whose
  key cannot be its name (`commission_data` → `CommissionData`), so you do not
  rename the schema key (the completeness guard pins key names).
- Per-variant `variant_names` (above) handles values the case conversion cannot
  recover.

## Semantic freeze

Put the LOAD-BEARING prose — the rule a maintainer must not silently change —
into the `$def`'s `description`, and let the generator emit it as a doc
comment. That survives hand-edits of the generated file (which CI rejects) and
keeps the frozen rationale visible in both the schema and the emitted code. Do
not let the only copy of the rationale live in the pre-generation doc comment
and then delete it.

## Cross-target reuse

One generator, `Target { banner, schema_rel, out_rel, files }` per schema. The
`out_rel` differs so the second schema regenerates into its own crate. Keep
each `banner` distinct so extending the generator does not rewrite the first
target's committed bytes.
