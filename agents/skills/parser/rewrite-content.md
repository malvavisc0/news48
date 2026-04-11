# Skill: rewrite-content

## Trigger
Always active — parser must produce simplified but faithful content.

## Rules
1. Rewrite article in simple, easy-to-read English.
2. Do NOT copy article content.
3. Remove noise, repetitions, filler.
4. Keep 2-4 short paragraphs, key facts and context.
5. Use clear, plain language.
6. Remove boilerplate like "The article discusses" or "Key facts include".

## Content via File
Always write content to temp file, then use `--content-file`:
```bash
cat > /tmp/parsed_ARTICLEID.txt << 'CONTENT_EOF'
Content here...
CONTENT_EOF
```
