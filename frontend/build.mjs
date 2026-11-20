import { build } from 'esbuild';
import { mkdir, readFile, writeFile } from 'node:fs/promises';

await mkdir('dist', { recursive: true });
await build({ entryPoints: ['src/main.tsx'], bundle: true, format: 'esm', outdir: 'dist/assets', entryNames: 'app', minify: true, sourcemap: false, target: ['es2020'], loader: { '.tsx': 'tsx', '.css': 'css' } });
const html = (await readFile('index.html', 'utf8')).replace('<script type="module" src="/src/main.tsx"></script>', '<link rel="stylesheet" href="/assets/app.css"/><script type="module" src="/assets/app.js"></script>');
await writeFile('dist/index.html', html);
console.log('React app bundled into dist/');
