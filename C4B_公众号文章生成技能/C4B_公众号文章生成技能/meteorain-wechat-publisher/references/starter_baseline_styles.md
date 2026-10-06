# WeChat Publisher — Style Reference

Standard inline CSS values for WeChat Official Account articles.
Modify these to create your own visual style.

## Typography

### H2 (section heading — WeChat's top-level heading)
```
font-size: 22px; font-weight: bold; line-height: 1.6;
color: #333; margin: 20px 0 10px 0;
```

### H3 (sub-heading)
```
font-size: 18px; font-weight: bold; line-height: 1.6;
color: #333; margin: 15px 0 8px 0;
```

### Body text (paragraphs)
```
font-size: 16px; line-height: 1.75; color: #333; margin: 10px 0;
```

### List items
```
font-size: 16px; line-height: 1.75; color: #333; margin: 5px 0;
```

## Code

### Inline code
```
background-color: #f5f5f5; color: #d73a49; font-size: 14px; padding: 2px 4px;
```

### Code block
```
background-color: #f6f8fa; color: #24292e; font-size: 14px;
line-height: 1.6; padding: 16px; margin: 10px 0;
```

## Structural

### Blockquote
```
background-color: #f9f9f9; color: #666; padding: 10px 15px;
margin: 10px 0; border-left: 4px solid #ddd;
```

### Table
```
border-collapse: collapse; margin: 10px 0; font-size: 14px;
```

### Table header cell (th)
```
background-color: #f6f8fa; color: #24292e; font-weight: bold;
padding: 8px; text-align: left; border: 1px solid #ddd;
```

### Table data cell (td)
```
padding: 8px; border: 1px solid #ddd; color: #333;
```

### Link
```
color: #0366d6; text-decoration: underline;
```

## Mobile Considerations

- **Minimum body text**: 16px (smaller is unreadable on phones)
- **Max width**: articles display at ~375px on most phones
- **Line height**: 1.75 is the sweet spot for Chinese text readability
- **Color**: avoid pure black (#000); #333 is softer on eyes
- **Images**: always set `max-width: 100%` to prevent overflow

## Customization Ideas

### Blue accent theme
```
h2 color: #1a73e8
blockquote border-left: 4px solid #1a73e8
blockquote background-color: #f0f7ff
```

### Warm theme
```
h2 color: #e65100
blockquote border-left: 4px solid #ff9800
blockquote background-color: #fff8e1
```

### Minimalist theme
```
h2 color: #333 (same as body)
blockquote border-left: 4px solid #999
blockquote background-color: #fafafa
```
