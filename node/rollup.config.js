import typescript from '@rollup/plugin-typescript';

export default {
  input: 'src/index.ts',
  output: [
    {
      file: 'dist/devlogs.cjs.js',
      format: 'cjs',
      sourcemap: true,
    },
    {
      file: 'dist/devlogs.esm.js',
      format: 'esm',
      sourcemap: true,
    },
  ],
  external: [
    'node:async_hooks',
    'node:http',
    'node:https',
    'node:fs',
    'node:path',
    'node:url',
    'async_hooks',
    'http',
    'https',
    'fs',
    'path',
    'url',
  ],
  plugins: [
    typescript({
      tsconfig: './tsconfig.json',
      declaration: true,
      declarationDir: 'dist',
    }),
  ],
};
