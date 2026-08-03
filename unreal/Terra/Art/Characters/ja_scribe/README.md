# J̌a — canonical look-development v001

This folder contains the first visual identity derived from the current
`terra-life` simulation export. It is reference art, not a rigged gameplay
asset.

## Source record

- Export: `export_ue/capital/people.json`
- Scene: `capital`
- Record index: `10`
- Name: `J̌a`
- Age: `54`
- Role: `scribe` / `писец`
- Simulation person: `real_person = true`
- Skin swatch: `#b98f6b`
- Clothing swatch: `#7a4a52`
- Traits: patience `0.26`, empathy `0.70`, piety `0.69`
- Beliefs: outsiders are dangerous `0.94`, authority is legitimate `0.94`

The export's numeric sex field is interpreted as female for this first visual
pass. That mapping must be confirmed against the simulator contract before the
identity is locked for production.

## Generated reference

- Lossless local file: `ja_scribe_lookdev_v001.png`
- Repository preview: `ja_scribe_lookdev_v001.jpg`
- Resolution: `1024 × 1536`
- PNG SHA-256: `66bafdd7a56874c9b131d67954ae9712fd42241347161bc2a41832b605972dc9`
- JPEG SHA-256: `73f9e015240be6cdb7ac3f57dd3bdf15860fa832ad987aa53667748cb3109aa6`
- Generated: `2026-08-02` (America/Los_Angeles)
- Intended use: MetaHuman identity/look reference and art-direction review

## Prompt

```text
Create a photorealistic cinematic character look-development portrait for an
Unreal Engine 5.8 game, based on a deterministic simulation NPC.

J̌a is a 54-year-old woman and professional scribe from Raflir, a vast coastal
desert metropolis in the alternate-history polity Sikyiþi. The simulation
labels the era "modernity" in year 500 CE because this civilization advanced
unusually early; the culture must feel internally evolved, not like present-day
Earth and not generic fantasy. Warm medium-brown skin approximately #b98f6b.
Clothing's dominant textile color is muted dark rose #7a4a52. Her expression
shows high empathy and strong religious conviction, restrained patience, and
the alert caution of someone who believes outsiders may be dangerous. Show age
honestly: fine lines, sun exposure, individual facial asymmetry, natural pores,
and no beauty retouching.

Use plausible high-skill desert-coastal textile construction reimagined for an
early-advanced civilization: breathable layered woven linen and fine wool,
muted dark-rose outer wrap, sand-colored underlayer, precise geometric
stitching, a practical archival sash, reed-and-metal stylus, and a thin writing
tablet. No logos, zippers, contemporary suit, medieval-European costume,
fantasy armor, sci-fi glow, or weapons. Hair is practical for hot weather with
subtle gray strands.

Single person, waist-up three-quarter portrait, hands partially visible holding
the tablet, eye-level 85 mm lens, neutral calm posture, looking just off camera.
The background is a sophisticated sunlit archive opening onto pale terraces and
a distant desert sea. Late-afternoon natural sunlight, documentary-authentic
color, extremely believable anatomy, skin, eyes, hair, and textiles. Clean,
unobstructed MetaHuman-quality facial reference. No text, watermark, collage,
split screen, or multiple views.
```

## Production path

1. Confirm the simulator's sex enum and approve the identity.
2. Produce neutral front/profile references or a clean 3D head scan/base mesh.
3. Conform the head/body through Mesh to MetaHuman and assemble the character.
4. Build groom, wardrobe, materials, physics assets, and LOD policy.
5. Drive face from audio/video capture; add body motion and interaction states.
6. Bind the MetaHuman actor to the stable simulation NPC identifier and save
   provenance for every generated or licensed asset.
