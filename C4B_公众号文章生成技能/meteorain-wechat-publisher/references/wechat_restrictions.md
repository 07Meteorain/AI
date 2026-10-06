# WeChat Official Account HTML Restrictions

A complete reference of what WeChat's editor allows and forbids.
Your converter must enforce these rules to produce working output.

## Allowed HTML Tags

```
p, h2, h3, ul, ol, li, span, img, a, table, tr, th, td, br
```

## Forbidden HTML Tags

| Tag | Why Forbidden | What To Do |
|-----|--------------|------------|
| `<h1>` | WeChat reserves h1 for article title | Convert to `<h2>` |
| `<div>` | Not rendered reliably | Convert to `<p>` or `<span>` |
| `<script>` | Security — always stripped | Remove entirely |
| `<style>` | CSS must be inline only | Move styles to `style=""` attributes |
| `<iframe>` | External embeds forbidden | Remove or convert to link |
| `<video>` | Must use WeChat's video embed | Remove or convert to link |
| `<audio>` | Must use WeChat's audio embed | Remove or convert to link |

## Forbidden HTML Attributes

| Attribute | Why Forbidden | What To Do |
|-----------|--------------|------------|
| `class` | No CSS classes in WeChat | Remove |
| `id` | No element IDs in WeChat | Remove |
| `onclick` etc. | No JavaScript events | Remove |

## CSS Rules

### Must be inline
Every element needs `style="..."` directly on the tag.

```html
<!-- ✅ Correct -->
<p style="font-size: 16px; color: #333;">Hello</p>

<!-- ❌ Wrong — WeChat strips this -->
<style>p { font-size: 16px; color: #333; }</style>
<p>Hello</p>

<!-- ❌ Wrong — WeChat strips class -->
<p class="body-text">Hello</p>
```

### Allowed CSS Properties
```
color, background-color, font-size, font-weight, font-style,
line-height, text-align, margin, padding, border, border-left,
border-collapse, text-decoration, display, vertical-align,
max-width, width
```

### Forbidden CSS
- `position`, `float`, `flex`, `grid` — layout properties
- `animation`, `transition` — motion properties
- `@media` queries — no responsive breakpoints
- Custom fonts via `@font-face`

## Image Rules

| Method | Works? | Notes |
|--------|--------|-------|
| `<img src="https://...">` | ⚠️ | Works if URL is accessible; WeChat may re-host |
| `<img src="data:image/png;base64,...">` | ✅ | WeChat converts to CDN-hosted on paste |
| `<img src="data:image/svg+xml;base64,...">` | ❌ | Disappears on save — WeChat can't re-upload SVG |
| Inline SVG (`<svg>...`) | ❌ | Stripped entirely |

**Best practice**: Use PNG base64 for self-contained images.
For photos, upload to WeChat media library and use the CDN URL.

## Article Limits

| Limit | Value |
|-------|-------|
| Max article length | ~20,000 Chinese characters |
| Max images | 100 per article |
| Max image size | 10 MB per image |
| Supported image formats | PNG, JPG, GIF |
| Max GIF size | 2 MB |

## Common Pitfalls

1. **Lost formatting after save**: Usually means you used forbidden tags or CSS
2. **Images disappearing**: SVG data URIs or broken external URLs
3. **Spacing issues**: WeChat collapses margins differently than browsers
4. **Code blocks broken**: Must use `<p>` with inline styles, not `<pre><code>`
5. **Tables too wide**: No horizontal scroll; consider splitting wide tables
