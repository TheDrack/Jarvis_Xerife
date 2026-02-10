# JARVIS PWA Icons

To complete the PWA setup, you need to add the following icon files to this directory:

## Required Icons

1. **icon-192.png** - 192x192 pixels PNG icon
2. **icon-512.png** - 512x512 pixels PNG icon

## Design Guidelines

- Background color: #0a0e27 (dark blue)
- Primary color: #00d4ff (cyan)
- Theme: Arc reactor / tech aesthetic
- Text: "JARVIS" in monospace font

## Temporary Solution

The manifest.json references these icons. Until you create them:

1. You can use a placeholder generator like: https://placeholder.com/
2. Or create simple icons with the JARVIS logo/text
3. Or use any 192x192 and 512x512 PNG images as placeholders

## Example SVG Template

```svg
<svg width="192" height="192" xmlns="http://www.w3.org/2000/svg">
  <rect width="192" height="192" rx="20" fill="#0a0e27"/>
  <circle cx="96" cy="96" r="60" fill="none" stroke="#00d4ff" stroke-width="4"/>
  <circle cx="96" cy="96" r="30" fill="#00d4ff"/>
  <text x="96" y="165" font-family="monospace" font-size="24" fill="#00d4ff" text-anchor="middle" font-weight="bold">JARVIS</text>
</svg>
```

Convert this SVG to PNG at 192x192 and 512x512 resolutions.

## Quick Generation

Use ImageMagick or online tools:

```bash
# If you have ImageMagick installed
convert icon.svg -resize 192x192 icon-192.png
convert icon.svg -resize 512x512 icon-512.png
```

Or use online tools like:
- https://cloudconvert.com/svg-to-png
- https://onlineconvertfree.com/convert-format/svg-to-png/
