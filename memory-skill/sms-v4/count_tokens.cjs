#!/usr/bin/env node
/**
 * Token counter for SMS memory system
 * Usage: node count_tokens.js <text or file>
 *        node count_tokens.js --hot   # Count hot tier tokens
 *        node count_tokens.js --all   # Count total memory tokens
 */
const t = require('@anthropic-ai/tokenizer');
const fs = require('fs');

const target = process.argv[2];

if (!target) {
    console.log('Usage: node count_tokens.js <text | file | --hot | --all | --claude>');
    process.exit(0);
}

if (target === '--claude') {
    const path = '/mnt/c/Users/64608/CLAUDE.md';
    const text = fs.readFileSync(path, 'utf-8');
    console.log(`CLAUDE.md: ${text.length} chars → ${t.countTokens(text)} tokens`);
    process.exit(0);
}

if (target === '--hot') {
    const path = '/home/lzx020508/.openclaw/workspace/memory/cache/memory_cache.json';
    const text = fs.readFileSync(path, 'utf-8');
    console.log(`Hot tier cache: ${text.length} chars → ${t.countTokens(text)} tokens`);
    process.exit(0);
}

if (target === '--consolidated') {
    const path = '/home/lzx020508/.openclaw/workspace/memory/curated/consolidated.json';
    const text = fs.readFileSync(path, 'utf-8');
    console.log(`Consolidated: ${text.length} chars → ${t.countTokens(text)} tokens`);
    process.exit(0);
}

if (target === '--all') {
    const paths = [
        ['CLAUDE.md', '/mnt/c/Users/64608/CLAUDE.md'],
        ['Hot cache', '/home/lzx020508/.openclaw/workspace/memory/cache/memory_cache.json'],
        ['Consolidated', '/home/lzx020508/.openclaw/workspace/memory/curated/consolidated.json'],
    ];
    let total = 0;
    for (const [name, path] of paths) {
        if (fs.existsSync(path)) {
            const text = fs.readFileSync(path, 'utf-8');
            const tokens = t.countTokens(text);
            console.log(`${name}: ${tokens} tokens`);
            total += tokens;
        }
    }
    console.log(`---\nTotal memory overhead: ${total} tokens`);
    process.exit(0);
}

if (fs.existsSync(target)) {
    const text = fs.readFileSync(target, 'utf-8');
    console.log(`File: ${target}`);
    console.log(`${text.length} chars → ${t.countTokens(text)} tokens`);
} else {
    console.log(`Text: "${target}"`);
    console.log(`${target.length} chars → ${t.countTokens(target)} tokens`);
}
