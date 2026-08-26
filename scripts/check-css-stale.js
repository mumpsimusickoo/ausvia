#!/usr/bin/env node
// Tailwind build pass, 2026-08-26. The compiled stylesheet is committed
// (see DEPLOYMENT.md / DECISIONS.md - Railway's deploy never runs Node),
// which means it can silently drift from tailwind.config.js/assets/css/
// input.css/the templates it's built from if someone edits a class name
// or a token and forgets to run `npm run build:css` before committing.
// This script is that forgetting-proof check: it rebuilds into a scratch
// file and fails loudly if the result differs from what's actually
// committed at app/static/css/tailwind.css, rather than relying on anyone
// remembering. Run via `npm run check:css` - add it to CI/pre-commit if
// this project ever gets either; for now it's a manual pre-deploy step
// (see DEPLOYMENT.md's checklist).

const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const root = path.resolve(__dirname, '..');
const committedPath = path.join(root, 'app', 'static', 'css', 'tailwind.css');
const tailwindBin = path.join(
  root, 'node_modules', '.bin', process.platform === 'win32' ? 'tailwindcss.cmd' : 'tailwindcss'
);

if (!fs.existsSync(committedPath)) {
  console.error('FAIL: app/static/css/tailwind.css does not exist - run `npm run build:css` first.');
  process.exit(1);
}

const scratchPath = path.join(os.tmpdir(), `ausvia-tailwind-check-${Date.now()}.css`);

try {
  execFileSync(tailwindBin, [
    '-c', path.join(root, 'tailwind.config.js'),
    '-i', path.join(root, 'assets', 'css', 'input.css'),
    '-o', scratchPath,
    '--minify',
  ], { stdio: 'pipe', shell: process.platform === 'win32' });

  const committed = fs.readFileSync(committedPath, 'utf8');
  const fresh = fs.readFileSync(scratchPath, 'utf8');

  if (committed === fresh) {
    console.log('OK: app/static/css/tailwind.css matches a fresh build. Nothing to rebuild.');
    process.exit(0);
  }

  console.error('FAIL: app/static/css/tailwind.css is STALE.');
  console.error('A fresh build (tailwind.config.js + assets/css/input.css + app/templates/**) produces different output than what is committed.');
  console.error('Run `npm run build:css` and commit the result before deploying.');
  console.error(`Committed size: ${committed.length} bytes. Fresh size: ${fresh.length} bytes.`);
  process.exit(1);
} finally {
  try { fs.unlinkSync(scratchPath); } catch (e) { /* scratch file, fine if it never existed */ }
}
